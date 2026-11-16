import unittest
from bblia_android_compat import adapt_java


class CompatibilityTests(unittest.TestCase):
    def test_counter_preserves_event_and_initial_value(self):
        source = '''public class MainActivity extends AppCompatActivity {
private int contador=0;
protected void onCreate(Bundle savedInstanceState) {
super.onCreate(savedInstanceState);setContentView(R.layout.activity_main);
final TextView textView=findViewById(R.id.text_view);
final Button botao=findViewById(R.id.button);
botao.setOnClickListener(new View.OnClickListener(){public void onClick(View v){contador++;textView.setText(String.valueOf(contador));}});
}}'''
        java, changes = adapt_java(source, 'com.bblia.test', 'Crie um contador com botao Somar')
        self.assertIn('extends Activity', java)
        self.assertIn('contador++;', java)
        self.assertIn('textView.setText(String.valueOf(contador))', java)
        self.assertIn('.setText("0")', java)
        self.assertIn('.setText("Somar")', java)
        self.assertNotIn('R.', java)
        self.assertNotIn('AppCompatActivity', java)
        self.assertEqual(len(changes), 2)

    def test_missing_image_resources_are_rejected(self):
        with self.assertRaises(ValueError):
            adapt_java('setImageResource(R.drawable.missing);', 'com.bblia.test')

    def test_unknown_widget_does_not_get_invented(self):
        with self.assertRaises(ValueError):
            adapt_java('setContentView(R.layout.main); Missing x=findViewById(R.id.x);', 'com.bblia.test')

    def test_standard_programmatic_body_is_kept(self):
        java, changes = adapt_java('setContentView(new TextView(this));', 'com.bblia.test')
        self.assertIn('setContentView(new TextView(this));', java)
        self.assertFalse(changes)

    def test_external_dependency_is_not_silently_removed(self):
        with self.assertRaises(ValueError):
            adapt_java('import androidx.fragment.Fragment;class MainActivity extends Activity{}', 'com.bblia.test')


if __name__ == '__main__':
    unittest.main()
