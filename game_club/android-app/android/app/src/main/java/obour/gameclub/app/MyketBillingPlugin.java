package obour.gameclub.app;

import android.content.pm.PackageManager;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONException;

import java.util.ArrayList;
import java.util.List;

import ir.myket.billingclient.IabHelper;
import ir.myket.billingclient.util.IabResult;
import ir.myket.billingclient.util.Purchase;

/**
 * خرید درون برنامه ای مایکت برای صفحه های برنامه (static/app.js: GCApp.iap).
 *
 * روی کتابخانهٔ رسمی مایکت (myket-billing-client). کلید عمومی RSA را سرور می دهد (me.settings.iap.key)
 * و با هر کار می آید؛ کتابخانه امضای هر خرید را با آن می سنجد و سرور (game_club/iap.py) دوباره می سنجد
 * و فقط بعد سکه می دهد. کارها صف ندارند: صفحه ها پشت هم می فرستند (gc.js).
 *
 * کدهای خطا برای صفحه ها: cancelled (کاربر بست)، owned (خرید قبلی هنوز consume نشده)،
 * unavailable (مایکت نیست یا پرداخت در دسترس نیست)، item (محصول در پنل مایکت نیست)، failed (بقیه).
 */
@CapacitorPlugin(name = "MyketBilling")
public class MyketBillingPlugin extends Plugin {
    private static final String MYKET = "ir.mservices.market";

    private IabHelper helper;
    private String key = "";
    private boolean ready;
    private boolean starting;
    private final List<Object[]> waiting = new ArrayList<>();

    private boolean installed() {
        try {
            getContext().getPackageManager().getApplicationInfo(MYKET, 0);
            return true;
        } catch (PackageManager.NameNotFoundException e) {
            return false;
        }
    }

    private static String codeOf(int response) {
        switch (response) {
            case IabHelper.BILLING_RESPONSE_RESULT_USER_CANCELED:
            case IabHelper.IABHELPER_USER_CANCELLED:
                return "cancelled";
            case IabHelper.BILLING_RESPONSE_RESULT_ITEM_ALREADY_OWNED:
                return "owned";
            case IabHelper.BILLING_RESPONSE_RESULT_BILLING_UNAVAILABLE:
                return "unavailable";
            case IabHelper.BILLING_RESPONSE_RESULT_ITEM_UNAVAILABLE:
                return "item";
            default:
                return "failed";
        }
    }

    private static JSObject toJs(Purchase p) {
        JSObject o = new JSObject();
        o.put("sku", p.getSku());
        o.put("token", p.getToken());
        o.put("orderId", p.getOrderId());
        o.put("payload", p.getDeveloperPayload());
        o.put("state", p.getPurchaseState());
        o.put("json", p.getOriginalJson());
        o.put("signature", p.getSignature());
        return o;
    }

    private void dispose() {
        if (helper != null) {
            try {
                helper.dispose();
            } catch (RuntimeException ignored) {
                // سرویس مایکت قبلا رفته
            }
        }
        helper = null;
        ready = false;
        starting = false;
    }

    /** کتابخانه یک بار برای هر کلید راه می افتد؛ کارهایی که وسط راه اندازی برسند منتظر می مانند. */
    private void withHelper(PluginCall call, Runnable then) {
        final String k = call.getString("key", "");
        if (k == null || k.isEmpty()) {
            call.reject("public key is missing", "unavailable");
            return;
        }
        getActivity().runOnUiThread(() -> {
            if (helper != null && !k.equals(key)) {
                dispose();
            }
            if (helper != null && ready) {
                then.run();
                return;
            }
            waiting.add(new Object[]{call, then});
            if (starting) {
                return;
            }
            key = k;
            starting = true;
            helper = new IabHelper(getContext(), k);
            helper.startSetup(result -> {
                starting = false;
                ready = result.isSuccess();
                List<Object[]> all = new ArrayList<>(waiting);
                waiting.clear();
                for (Object[] w : all) {
                    if (ready) {
                        ((Runnable) w[1]).run();
                    } else {
                        ((PluginCall) w[0]).reject(result.getMessage(), codeOf(result.getResponse()));
                    }
                }
                if (!ready) {
                    dispose();
                }
            });
        });
    }

    @PluginMethod
    public void available(PluginCall call) {
        JSObject o = new JSObject();
        o.put("installed", installed());
        call.resolve(o);
    }

    @PluginMethod
    public void purchase(PluginCall call) {
        final String sku = call.getString("sku", "");
        final String payload = call.getString("payload", "");
        if (sku == null || sku.isEmpty()) {
            call.reject("sku is missing", "failed");
            return;
        }
        withHelper(call, () -> {
            try {
                helper.launchPurchaseFlow(getActivity(), sku, (IabResult result, Purchase p) -> {
                    if (result.isSuccess() && p != null) {
                        call.resolve(toJs(p));
                    } else {
                        call.reject(result.getMessage(), codeOf(result.getResponse()));
                    }
                }, payload);
            } catch (RuntimeException e) {
                call.reject(String.valueOf(e.getMessage()), "failed");
            }
        });
    }

    /** خریدهای consume نشده (مثلا برنامه وسط کار بسته شد)؛ صفحه ها دوباره به سرور می فرستند. */
    @PluginMethod
    public void owned(PluginCall call) {
        if (!installed()) {
            JSObject o = new JSObject();
            o.put("purchases", new JSArray());
            call.resolve(o);
            return;
        }
        withHelper(call, () -> {
            try {
                helper.queryInventoryAsync(false, null, (result, inv) -> {
                    if (result.isFailure() || inv == null) {
                        call.reject(result.getMessage(), codeOf(result.getResponse()));
                        return;
                    }
                    JSArray list = new JSArray();
                    for (Purchase p : inv.getAllPurchases()) {
                        if (IabHelper.ITEM_TYPE_INAPP.equals(p.getItemType())) {
                            list.put(toJs(p));
                        }
                    }
                    JSObject o = new JSObject();
                    o.put("purchases", list);
                    call.resolve(o);
                });
            } catch (RuntimeException e) {
                call.reject(String.valueOf(e.getMessage()), "failed");
            }
        });
    }

    /** بعد از جواب سرور: همان بسته دوباره خریدنی می شود. */
    @PluginMethod
    public void consume(PluginCall call) {
        final String json = call.getString("json", "");
        final String signature = call.getString("signature", "");
        final Purchase p;
        try {
            p = new Purchase(IabHelper.ITEM_TYPE_INAPP, json, signature);
        } catch (JSONException e) {
            call.reject("bad purchase", "failed");
            return;
        }
        withHelper(call, () -> {
            try {
                helper.consumeAsync(p, (purchase, result) -> {
                    if (result.isSuccess()) {
                        call.resolve();
                    } else {
                        call.reject(result.getMessage(), codeOf(result.getResponse()));
                    }
                });
            } catch (RuntimeException e) {
                call.reject(String.valueOf(e.getMessage()), "failed");
            }
        });
    }

    @Override
    protected void handleOnDestroy() {
        dispose();
    }
}
