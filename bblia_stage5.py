"""Stage 5: truthful capability and readiness reporting for BBLIA autonomous work."""
import os
import bblia_runtime as runtime
import bblia_documents as documents
from bblia_gemini import configured as gemini_configured

def capabilities():
 def status(fn):
  try:return fn()
  except Exception:return {'state':'unavailable'}
 return {
  'stage':5,
  'features':{
   'projects':{'state':'ready','detail':'Creates and revises project source files; files are downloadable.'},
   'javascript_tests':{'state':status(lambda: {'state':'ready' if hasattr(runtime,'run') or hasattr(runtime,'execute') else 'available_module'}).get('state','unavailable'),'detail':'Sandboxed JavaScript logic tests, not full browser or APK testing.'},
   'documents':{'state':status(lambda: {'state':'ready' if hasattr(documents,'generate') or hasattr(documents,'create') else 'available_module'}).get('state','unavailable'),'detail':'Structured document generation; output must be reviewed.'},
   'android_apk':{'state':'requires_connected_computer','detail':'Compilation requires an authorized connected computer, Android SDK and verified build output.'},
   'computer_control':{'state':'requires_owner_connection','detail':'Only via user-authorized Desktop Commander; no unrestricted access.'},
   'tvbox_diagnostics':{'state':'requires_owner_pairing','detail':'Device pairing and scoped credentials required; launcher is not modified by this status check.'},
   'openai_agent':{'state':'configured' if bool(os.getenv('OPENAI_API_KEY')) else 'missing_key','detail':'Paid model execution requires per-task authorization.'},
   'gemini_agent':{'state':'configured' if gemini_configured() else 'missing_key','detail':'Provider availability and quota may change.'}
  },
  'fully_autonomous':False,
  'requires_real_device_tests':True
 }
