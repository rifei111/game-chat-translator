package com.rifei.gt;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;

/**
 * 安卓壳：本地 assets 里的 phone 页面，WebSocket 连同一 WiFi 下的 PC 中继。
 * 不做任何网络转发，只渲染界面 + 提供剪贴板、相机扫码桥接。
 */
public class MainActivity extends Activity {

    private static final int REQ_SCAN = 1001;
    private static final int REQ_PICK = 1002;

    private WebView web;
    private Uri pendingScanUri;
    private File pendingScanFile;
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
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        if (requestCode == REQ_SCAN) {
            if (resultCode == RESULT_OK && pendingScanUri != null) {
                handleCapturedScan(pendingScanUri);
            } else {
                evalJs("window.onNativeScanCancel && window.onNativeScanCancel()");
                cleanupScan();
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

    private void handleCapturedScan(Uri uri) {
        try {
            Bitmap bmp = decodeSampled(uri, 1600);
            if (bmp == null) {
                evalJs("window.onNativeScanError && window.onNativeScanError('无法读取照片')");
                cleanupScan();
                return;
            }
            bmp = orientBitmap(bmp, uri);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            bmp.compress(Bitmap.CompressFormat.JPEG, 86, out);
            bmp.recycle();

            String dataUrl = "data:image/jpeg;base64,"
                    + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP);
            evalJs("window.onNativeScanImage && window.onNativeScanImage("
                    + JSONObject.quote(dataUrl) + ")");
        } catch (Exception e) {
            evalJs("window.onNativeScanError && window.onNativeScanError("
                    + JSONObject.quote(String.valueOf(e.getMessage())) + ")");
        } finally {
            cleanupScan();
        }
    }

    private Bitmap decodeSampled(Uri uri, int maxSide) throws Exception {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        try (InputStream in = getContentResolver().openInputStream(uri)) {
            BitmapFactory.decodeStream(in, null, bounds);
        }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null;

        int sample = 1;
        while (Math.max(bounds.outWidth, bounds.outHeight) / sample > maxSide * 2) {
            sample *= 2;
        }
        BitmapFactory.Options opts = new BitmapFactory.Options();
        opts.inSampleSize = sample;
        Bitmap bmp;
        try (InputStream in = getContentResolver().openInputStream(uri)) {
            bmp = BitmapFactory.decodeStream(in, null, opts);
        }
        if (bmp == null) return null;

        int w = bmp.getWidth();
        int h = bmp.getHeight();
        int longest = Math.max(w, h);
        if (longest > maxSide) {
            float scale = maxSide / (float) longest;
            Bitmap scaled = Bitmap.createScaledBitmap(
                    bmp, Math.round(w * scale), Math.round(h * scale), true);
            if (scaled != bmp) bmp.recycle();
            bmp = scaled;
        }
        return bmp;
    }

    private Bitmap orientBitmap(Bitmap bmp, Uri uri) {
        try (InputStream in = getContentResolver().openInputStream(uri)) {
            ExifInterface exif = new ExifInterface(in);
            int orientation = exif.getAttributeInt(
                    ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL);
            Matrix m = new Matrix();
            switch (orientation) {
                case ExifInterface.ORIENTATION_ROTATE_90:
                    m.postRotate(90);
                    break;
                case ExifInterface.ORIENTATION_ROTATE_180:
                    m.postRotate(180);
                    break;
                case ExifInterface.ORIENTATION_ROTATE_270:
                    m.postRotate(270);
                    break;
                case ExifInterface.ORIENTATION_FLIP_HORIZONTAL:
                    m.postScale(-1, 1);
                    break;
                case ExifInterface.ORIENTATION_FLIP_VERTICAL:
                    m.postScale(1, -1);
                    break;
                case ExifInterface.ORIENTATION_TRANSPOSE:
                    m.postRotate(90);
                    m.postScale(-1, 1);
                    break;
                case ExifInterface.ORIENTATION_TRANSVERSE:
                    m.postRotate(270);
                    m.postScale(-1, 1);
                    break;
                default:
                    return bmp;
            }
            Bitmap rotated = Bitmap.createBitmap(
                    bmp, 0, 0, bmp.getWidth(), bmp.getHeight(), m, true);
            if (rotated != bmp) bmp.recycle();
            return rotated;
        } catch (Exception e) {
            return bmp;
        }
    }

    private void cleanupScan() {
        pendingScanUri = null;
        if (pendingScanFile != null) {
            //noinspection ResultOfMethodCallIgnored
            pendingScanFile.delete();
            pendingScanFile = null;
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
         * 调起系统相机拍二维码。结果通过 window.onNativeScanImage(dataUrl) 回传，
         * 由 phone/app.js 本地用 jsQR 解码；照片不会上传到服务器。
         */
        @JavascriptInterface
        public void scanQRCode() {
            runOnUiThread(() -> {
                try {
                    File dir = new File(getCacheDir(), "scan");
                    if (!dir.exists() && !dir.mkdirs()) {
                        throw new IllegalStateException("无法创建扫码缓存目录");
                    }
                    File photo = new File(dir, "qr_" + System.currentTimeMillis() + ".jpg");
                    Uri uri = FileProvider.getUriForFile(
                            MainActivity.this, getPackageName() + ".fileprovider", photo);

                    pendingScanFile = photo;
                    pendingScanUri = uri;

                    Intent capture = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    capture.putExtra(MediaStore.EXTRA_OUTPUT, uri);
                    capture.setClipData(ClipData.newRawUri("scan", uri));
                    capture.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                            | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    startActivityForResult(capture, REQ_SCAN);
                } catch (Exception e) {
                    cleanupScan();
                    Toast.makeText(MainActivity.this, "无法打开相机，请检查相机权限",
                            Toast.LENGTH_SHORT).show();
                    evalJs("window.onNativeScanError && window.onNativeScanError('无法打开相机')");
                }
            });
        }
    }
}
