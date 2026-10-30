package obour.gameclub.app;

import android.os.Bundle;

import androidx.activity.EdgeToEdge;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // لبه تا لبه روی همهٔ اندرویدها (اندروید ۱۵ خودش اجباری اش کرده). بدون این، روی اندروید قدیمی تر برنامه
        // خودش زیر نوار وضعیت بود و پلاگین SystemBars یک بار دیگر به اندازهٔ همان نوار فاصله می گذاشت
        EdgeToEdge.enable(this);
        // پلاگین های خود برنامه (نه از npm): خرید درون برنامه ای مایکت، نوتیفیکیشن گوشی و رنگ پشت نوارها
        registerPlugin(MyketBillingPlugin.class);
        registerPlugin(AsoPushPlugin.class);
        registerPlugin(AsoUiPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
