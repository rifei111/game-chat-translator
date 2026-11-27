package com.rifei.gt;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

import org.json.JSONObject;

/**
 * 安卓壳：本地 assets 里的 phone 页面，WebSocket 连同一 WiFi 下的 PC 中继。
 * 扫码使用 ZXing 的实时相机预览，不拍照、不经过相册。
 */
public class MainActivity extends Activity {

    private static final int REQ_CAMERA = 1003;
    private static final int REQ_PICK = 1002;

    private WebView web;
    private ValueCallback<Uri[]> pendingFileCallback;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        web.addJavascriptInterface(new Bridge(), "GTBridge");
        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (pendingFileCallback != null) {
                    pendingFileCallback.onReceiveValue(null);
                }
                pendingFileCallback = callback;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("image/*");
                try {
                    startActivityForResult(Intent.createChooser(pick, "选择二维码图片"), REQ_PICK);
                    return true;
                } catch (ActivityNotFoundException e) {
                    pendingFileCallback = null;
                    callback.onReceiveValue(null);
                    return false;
                }
            }
        });
        web.loadUrl("file:///android_asset/phone/index.html");
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == REQ_CAMERA) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                launchLiveScanner();
            } else {
                Toast.makeText(this, "需要相机权限才能实时扫码", Toast.LENGTH_SHORT).show();
                evalJs("window.onNativeScanError && window.onNativeScanError('需要相机权限')");
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        // ZXing 扫码 Activity 的结果，优先处理。
        IntentResult scanResult = IntentIntegrator.parseActivityResult(requestCode, resultCode, data);
        if (scanResult != null) {
            String text = scanResult.getContents();
            if (text != null && !text.trim().isEmpty()) {
                evalJs("window.onNativeScanText && window.onNativeScanText("
                        + JSONObject.quote(text) + ")");
            } else {
                evalJs("window.onNativeScanCancel && window.onNativeScanCancel()");
            }
            return;
        }

        if (requestCode == REQ_PICK) {
            Uri[] result = null;
            if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                result = new Uri[]{data.getData()};
            }
            if (pendingFileCallback != null) {
                pendingFileCallback.onReceiveValue(result);
                pendingFileCallback = null;
            }
        }
    }

    private void launchLiveScanner() {
        try {
            IntentIntegrator integrator = new IntentIntegrator(this);
            integrator.setCaptureActivity(PortraitCaptureActivity.class);
            integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE);
            integrator.setPrompt("将电脑上的二维码放入框内");
            integrator.setBeepEnabled(false);
            integrator.setBarcodeImageEnabled(false);
            integrator.setOrientationLocked(true);
            integrator.initiateScan();
        } catch (Exception e) {
            Toast.makeText(this, "无法打开相机", Toast.LENGTH_SHORT).show();
            evalJs("window.onNativeScanError && window.onNativeScanError('无法打开相机')");
        }
    }

    private void evalJs(String js) {
        if (web != null) web.post(() -> web.evaluateJavascript(js, null));
    }

    /** 供页面调用：写系统剪贴板（WebView 里 navigator.clipboard 不可用时兜底）。 */
    public class Bridge {
        @JavascriptInterface
        public void copyText(String text) {
            ClipboardManager cm =
                    (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm != null) {
                cm.setPrimaryClip(ClipData.newPlainText("gt", text == null ? "" : text));
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "已复制", Toast.LENGTH_SHORT).show());
            }
        }

        /**
         * 打开 ZXing 实时扫码界面：相机预览连续识别二维码。
         * 结果通过 window.onNativeScanText(text) 回传，不拍照、不落盘。
         */
        @JavascriptInterface
        public void scanQRCode() {
            runOnUiThread(() -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                        && checkSelfPermission(Manifest.permission.CAMERA)
                        != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAMERA);
                    return;
                }
                launchLiveScanner();
            });
        }
    }
}
