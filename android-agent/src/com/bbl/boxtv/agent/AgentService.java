package com.bbl.boxtv.agent;
import android.app.*;import android.content.*;import android.content.pm.*;import android.net.*;import android.os.*;import org.json.*;
import java.io.*;import java.net.*;import java.util.*;import java.util.concurrent.*;
public class AgentService extends Service {
 private final ScheduledExecutorService loop=Executors.newSingleThreadScheduledExecutor();
 private volatile boolean stopped=false;private String token="",device="";
 public static void start(Context c){Intent i=new Intent(c,AgentService.class);if(Build.VERSION.SDK_INT>=26)c.startForegroundService(i);else c.startService(i);}
 public void onCreate(){super.onCreate();if(Build.VERSION.SDK_INT>=26){NotificationChannel ch=new NotificationChannel("bblia_agent","BBLIA controle remoto",NotificationManager.IMPORTANCE_LOW);((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(ch);}Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,"bblia_agent"):new Notification.Builder(this);startForeground(901,b.setContentTitle("BBLIA Agente").setContentText("Controle remoto do painel ativado").setSmallIcon(android.R.drawable.ic_menu_manage).setOngoing(true).build());loop.scheduleWithFixedDelay(()->{try{poll();}catch(Exception e){android.util.Log.w("BBLIAAgent","Conexão indisponível: "+e.getClass().getSimpleName());}},1,8,TimeUnit.SECONDS);}
 public int onStartCommand(Intent i,int flags,int id){return START_STICKY;}
 public IBinder onBind(Intent i){return null;}
 public void onDestroy(){stopped=true;loop.shutdownNow();super.onDestroy();}
 private String read(File f)throws Exception{try(InputStream in=new FileInputStream(f)){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>400000)throw new IOException("Arquivo grande");}return out.toString("UTF-8");}}
 private void write(File f,String text)throws Exception{File temp=new File(f.getPath()+".tmp");try(FileOutputStream out=new FileOutputStream(temp)){out.write(text.getBytes("UTF-8"));out.getFD().sync();}if(!temp.renameTo(f))throw new IOException("Não foi possível salvar estado");}
 private JSONObject http(String path,JSONObject data)throws Exception{
  if(!token.matches("[A-Za-z0-9_-]{30,100}"))throw new IOException("Vínculo ausente");
  javax.net.ssl.HttpsURLConnection c=(javax.net.ssl.HttpsURLConnection)new URL("https://152.67.55.60"+path).openConnection();c.setConnectTimeout(15000);c.setReadTimeout(20000);c.setRequestProperty("Authorization","Bearer "+token);c.setInstanceFollowRedirects(false);
  try{if(data!=null){c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");try(OutputStream out=c.getOutputStream()){out.write(data.toString().getBytes("UTF-8"));}}
   if(c.getResponseCode()!=200)throw new IOException("HTTP "+c.getResponseCode());try(InputStream in=c.getInputStream()){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[4096];int n;while((n=in.read(buffer))!=-1){out.write(buffer,0,n);if(out.size()>400000)throw new IOException("Resposta grande");}return new JSONObject(out.toString("UTF-8"));}
  }finally{c.disconnect();}
 }
 private void poll()throws Exception{
  if(stopped)return;JSONObject link=new JSONObject(read(new File(getFilesDir(),"link.json")));token=link.getString("token");device=link.getString("device_id");
  File outbox=new File(getFilesDir(),"outbox.json"),inflight=new File(getFilesDir(),"inflight.json");
  if(outbox.isFile()){JSONObject pending=new JSONObject(read(outbox));http("/api/agent/v1/results/"+pending.getString("id"),pending.getJSONObject("result"));if(!outbox.delete())return;if(inflight.exists())inflight.delete();}
  if(inflight.isFile()){
   JSONObject interrupted=new JSONObject(read(inflight));JSONObject result=recover(interrupted);write(outbox,new JSONObject().put("id",interrupted.getString("id")).put("result",result).toString());return;
  }
  JSONObject reply=http("/api/agent/v1/commands",null);JSONObject job=reply.optJSONObject("job");if(job==null)return;
  String id=job.getString("id");if(!id.matches("[A-Za-z0-9_-]{12,80}"))throw new IOException("ID inválido");write(inflight,job.toString());
  JSONObject result;
  try{if("diagnose".equals(job.getString("operation")))result=new JSONObject().put("status","completed").put("report",report());else if("uninstall".equals(job.getString("operation")))result=uninstall(job.getJSONObject("payload").getJSONArray("packages"));else result=new JSONObject().put("status","failed").put("error","Operação não disponível");}
  catch(Exception e){result=new JSONObject().put("status","failed").put("error",e.getMessage()==null?e.getClass().getSimpleName():e.getMessage());}
  write(outbox,new JSONObject().put("id",id).put("result",result).toString());android.util.Log.i("BBLIAAgent","Resultado registrado: "+id+" "+result.optString("status"));
 }
 private JSONObject recover(JSONObject job)throws Exception{
  if("diagnose".equals(job.optString("operation")))return new JSONObject().put("status","completed").put("report",report());
  JSONArray rows=new JSONArray(),packages=job.optJSONObject("payload").optJSONArray("packages");
  if(packages!=null)for(int n=0;n<packages.length();n++){String pkg=packages.getString(n);rows.put(new JSONObject().put("package",pkg).put("message",installed(pkg)?"Execução interrompida; remoção não repetida automaticamente":"Ausência do aplicativo confirmada após recuperação"));}
  return new JSONObject().put("status","partial").put("results",rows);
 }
 private String root(String command)throws Exception{
  java.lang.Process p=new ProcessBuilder("/system/xbin/su","-c",command).redirectErrorStream(true).start();
  ExecutorService reader=Executors.newSingleThreadExecutor();
  Future<String> output=reader.submit(()->{
   try(InputStream in=p.getInputStream()){
    ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[1024];int n;
    while((n=in.read(b))!=-1){if(out.size()<16000)out.write(b,0,Math.min(n,16000-out.size()));}
    return out.toString("UTF-8").trim();
   }
  });
  try{
   p.getOutputStream().close();
   long end=SystemClock.elapsedRealtime()+20000;int code;
   while(true){try{code=p.exitValue();break;}catch(IllegalThreadStateException e){
    if(SystemClock.elapsedRealtime()>end)throw new IOException("Root nao respondeu a tempo");
    Thread.sleep(80);
   }}
   String result=output.get(3,TimeUnit.SECONDS);
   if(code!=0)throw new IOException("Root recusado (codigo "+code+"): "+result.substring(0,Math.min(180,result.length())));
   return result;
  }finally{p.destroy();reader.shutdownNow();}
 }
 private boolean installed(String pkg){try{getPackageManager().getApplicationInfo(pkg,0);return true;}catch(PackageManager.NameNotFoundException e){return false;}}
 private boolean protectedPackage(String pkg)throws Exception{
  if(!pkg.matches("[A-Za-z0-9_]+(?:\\.[A-Za-z0-9_]+)+")||pkg.startsWith("com.bbl.")||pkg.equals("android"))return true;
  ApplicationInfo app=getPackageManager().getApplicationInfo(pkg,0);return (app.flags&(ApplicationInfo.FLAG_SYSTEM|ApplicationInfo.FLAG_UPDATED_SYSTEM_APP))!=0;
 }
 private JSONObject uninstall(JSONArray packages)throws Exception{
  if(packages.length()<1||packages.length()>10)throw new IOException("Lista de aplicativos inválida");
  if(!root("id").contains("uid=0"))throw new IOException("Este agente não recebeu permissão de root para desinstalar silenciosamente");
  JSONArray rows=new JSONArray();boolean ok=true;
  for(int n=0;n<packages.length();n++){String pkg=packages.getString(n),message;
   if(!installed(pkg))message="Aplicativo já ausente; nenhuma remoção executada";
   else if(protectedPackage(pkg)){message="Aplicativo protegido; nenhuma alteração executada";ok=false;}
   else{String output=root("pm uninstall --user 0 "+pkg);boolean removed=!installed(pkg);message=removed?"Desinstalação confirmada":"Não removido: "+output.substring(0,Math.min(250,output.length()));if(!removed)ok=false;}
   rows.put(new JSONObject().put("package",pkg).put("message",message));
  }
  return new JSONObject().put("status",ok?"completed":"partial").put("results",rows);
 }
 private JSONObject report()throws Exception{
  JSONObject r=new JSONObject();r.put("device_id",device);r.put("agent_version","1.0.0");r.put("model",Build.MANUFACTURER+" "+Build.MODEL);r.put("android",Build.VERSION.RELEASE);r.put("sdk",Build.VERSION.SDK_INT);r.put("abi",Build.SUPPORTED_ABIS[0]);r.put("uptime_seconds",SystemClock.elapsedRealtime()/1000);
  ActivityManager.MemoryInfo mem=new ActivityManager.MemoryInfo();((ActivityManager)getSystemService(ACTIVITY_SERVICE)).getMemoryInfo(mem);r.put("memory_free",mem.availMem);r.put("memory_total",mem.totalMem);r.put("low_memory",mem.lowMemory);
  StatFs disk=new StatFs(Environment.getDataDirectory().getAbsolutePath());r.put("storage_free",disk.getAvailableBytes());r.put("storage_total",disk.getTotalBytes());
  android.net.ConnectivityManager cm=(android.net.ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);NetworkInfo net=cm.getActiveNetworkInfo();r.put("network",net==null?"desconectada":net.getTypeName()+" "+net.getState());
  try{String detail=root("id");r.put("root",detail.contains("uid=0"));if(!detail.contains("uid=0"))r.put("root_detail",detail.substring(0,Math.min(180,detail.length())));}catch(Exception e){r.put("root",false);r.put("root_detail",String.valueOf(e.getMessage()));}
  try{File[] zones=new File("/sys/class/thermal").listFiles();if(zones!=null)for(File zone:zones)if(zone.getName().startsWith("thermal_zone")){double t=Double.parseDouble(read(new File(zone,"temp")).trim());if(t>1000)t/=1000;if(t>0&&t<150){r.put("temperature_c",t);break;}}}catch(Exception ignored){}
  JSONArray apps=new JSONArray();PackageManager pm=getPackageManager();List<PackageInfo> list=pm.getInstalledPackages(0);for(PackageInfo p:list){if(apps.length()>=400)break;ApplicationInfo a=p.applicationInfo;if(a==null)continue;apps.put(new JSONObject().put("package",p.packageName).put("label",String.valueOf(pm.getApplicationLabel(a))).put("version",p.versionName==null?"":p.versionName).put("system",(a.flags&(ApplicationInfo.FLAG_SYSTEM|ApplicationInfo.FLAG_UPDATED_SYSTEM_APP))!=0).put("enabled",a.enabled));}r.put("apps",apps);return r;
 }
}
