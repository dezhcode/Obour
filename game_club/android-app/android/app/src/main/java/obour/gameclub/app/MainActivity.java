package obour.gameclub.app;

import android.content.res.Configuration;
import android.graphics.Color;
import android.os.Bundle;

import androidx.activity.EdgeToEdge;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // پلاگین های خود برنامه (نه از npm): خرید درون برنامه ای مایکت، نوتیفیکیشن گوشی و رنگ پشت نوارها
        registerPlugin(MyketBillingPlugin.class);
        registerPlugin(AsoPushPlugin.class);
        registerPlugin(AsoUiPlugin.class);
        super.onCreate(savedInstanceState);
        // لبه تا لبه روی همهٔ اندرویدها (اندروید ۱۵ خودش اجباری اش کرده)؛ بعد از super تا قالب برنامه (بی نوار
        // عنوان) نشسته باشد. بدون این، روی اندروید قدیمی تر برنامه خودش زیر نوار وضعیت بود و پلاگین SystemBars
        // یک بار دیگر به اندازهٔ همان نوار فاصله می گذاشت
        EdgeToEdge.enable(this);
        // پشت نوار وضعیت تا وقتی صفحه رنگ خودش را بدهد (AsoUiPlugin): زمینهٔ پوستهٔ روشن یا تیره
        boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        getWindow().getDecorView().setBackgroundColor(night ? Color.parseColor("#0F1218") : Color.parseColor("#F4F5F8"));
    }
}
