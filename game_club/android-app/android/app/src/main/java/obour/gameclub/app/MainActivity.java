package obour.gameclub.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // پلاگین های خود برنامه (نه از npm): خرید درون برنامه ای مایکت و نوتیفیکیشن گوشی
        registerPlugin(MyketBillingPlugin.class);
        registerPlugin(AsoPushPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
