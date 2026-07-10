"""HTML 內容加密工具 — 把明文 HTML 變成「需密碼解鎖」的單檔 HTML。

純前端解密（Web Crypto API：PBKDF2-SHA256 + AES-GCM-256），原始碼只剩密文，
看 source 也無法繞過。用於對外發布（GitHub Pages demo / 分享給委員）。

⚠️ 明文 HTML 是真實來源（由 inject/build 維護）；本工具只負責「發布前加密」，
   不要拿加密產物去跑 inject/build。

用法：
  python3 encrypt_html.py <明文.html> <輸出.html> <密碼>
  （密碼必填，刻意不寫死於腳本，避免密碼隨腳本進入 repo）
"""
import base64
import os
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 250000


def encrypt(plaintext: str, password: str):
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=ITERATIONS).derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)  # ciphertext || 16-byte tag
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return b64(salt), b64(iv), b64(ct)


SHELL = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · 受保護</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%8F%9D%EF%B8%8F%3C/text%3E%3C/svg%3E">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { min-height: 100vh; display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, "PingFang TC", "Noto Sans TC", system-ui, sans-serif;
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8c 55%, #4a90c2 100%); padding: 24px; }
  .card { width: 100%; max-width: 380px; background: #fff; border-radius: 18px;
    box-shadow: 0 20px 60px rgba(15,42,68,.35); padding: 40px 32px; text-align: center; }
  .badge { width: 56px; height: 56px; margin: 0 auto 18px; border-radius: 14px;
    background: #1e3a5f; color: #fff; font-size: 28px; display: flex; align-items: center; justify-content: center; }
  h1 { font-size: 20px; color: #1e3a5f; font-weight: 700; letter-spacing: .5px; }
  .sub { margin-top: 8px; font-size: 13.5px; color: #64748b; line-height: 1.6; }
  .field { margin-top: 26px; text-align: left; }
  label { font-size: 12.5px; color: #475569; font-weight: 600; }
  input { width: 100%; margin-top: 7px; padding: 13px 15px; font-size: 16px;
    border: 1.5px solid #cbd5e1; border-radius: 11px; outline: none; transition: border-color .15s; letter-spacing: 2px; }
  input:focus { border-color: #2d5a8c; }
  button { width: 100%; margin-top: 18px; padding: 13px; font-size: 15px; font-weight: 700; color: #fff;
    background: #1e3a5f; border: none; border-radius: 11px; cursor: pointer; transition: background .15s; }
  button:hover { background: #2d5a8c; }
  button:disabled { background: #94a3b8; cursor: default; }
  .status { margin-top: 14px; font-size: 13px; min-height: 18px; }
  .status.err { color: #dc2626; }
  .status.ok { color: #2d5a8c; }
  .foot { margin-top: 22px; font-size: 11.5px; color: #94a3b8; }
</style>
</head>
<body>
  <div class="card">
    <div class="badge">&#128274;</div>
    <h1>__TITLE__</h1>
    <p class="sub">__SUBTITLE__<br>請輸入密碼以瀏覽。</p>
    <div class="field">
      <label for="pw">密碼</label>
      <input id="pw" type="password" inputmode="numeric" autocomplete="off" placeholder="請輸入密碼" autofocus>
    </div>
    <button id="btn">解鎖瀏覽</button>
    <div class="status" id="status"></div>
    <div class="foot">__FOOTHINT__</div>
  </div>
<script>
  const SALT="__SALT__", IV="__IV__", CT="__CT__", ITER=__ITER__;
  const b64d = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const $ = id => document.getElementById(id);
  async function unlock() {
    const pw = $("pw").value;
    const st = $("status");
    if (!pw) { st.className = "status err"; st.textContent = "請輸入密碼"; return; }
    $("btn").disabled = true; st.className = "status ok"; st.textContent = "解密中…";
    try {
      const km = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveKey"]);
      const key = await crypto.subtle.deriveKey(
        { name: "PBKDF2", salt: b64d(SALT), iterations: ITER, hash: "SHA-256" },
        km, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
      const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64d(IV) }, key, b64d(CT));
      const html = new TextDecoder().decode(pt);
      __RENDER__
    } catch (e) {
      $("btn").disabled = false; st.className = "status err"; st.textContent = "密碼錯誤，請重試";
      $("pw").select();
    }
  }
  $("btn").addEventListener("click", unlock);
  $("pw").addEventListener("keydown", e => { if (e.key === "Enter") unlock(); });
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) < 4:
        sys.exit("用法: python3 encrypt_html.py <明文.html> <輸出.html> <密碼> [鎖定畫面標題] [鎖定畫面副標]\n"
                 "（密碼必填，刻意不寫死於腳本，避免進 repo；標題/副標可選，預設為社區財報文案）")
    src, out, password = sys.argv[1], sys.argv[2], sys.argv[3]
    title = sys.argv[4] if len(sys.argv) > 4 else "受保護頁面"
    subtitle = (sys.argv[5] if len(sys.argv) > 5 else
                "社區財務透明儀表板，內容僅供本社區住戶與委員瀏覽。")
    foot_hint = ("" if len(sys.argv) > 5 else
                 "密碼請見社區公告，或洽管理委員會<br>")  # 自訂副標時不附預設指引
    # 解密後渲染方式：blob（預設，財報圖表需乾淨重載）或 inline（document.write，保留網址、iOS 較穩）
    mode = sys.argv[6] if len(sys.argv) > 6 else "blob"
    render = ('document.open("text/html","replace"); document.write(html); document.close();'
              if mode == "inline" else
              'const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" })); location.replace(url);')
    plaintext = open(src, encoding="utf-8").read()
    salt, iv, ct = encrypt(plaintext, password)
    shell = (SHELL.replace("__SALT__", salt).replace("__IV__", iv)
             .replace("__CT__", ct).replace("__ITER__", str(ITERATIONS))
             .replace("__TITLE__", title).replace("__SUBTITLE__", subtitle)
             .replace("__FOOTHINT__", foot_hint)
             .replace("__RENDER__", render))
    with open(out, "w", encoding="utf-8") as f:
        f.write(shell)
    print(f"✅ 加密 {os.path.basename(src)} ({len(plaintext):,} chars) → {out}")
    print(f"   密碼: {password}（PBKDF2-SHA256 {ITERATIONS} 次 + AES-GCM-256）")
    print(f"   產物 {os.path.getsize(out):,} bytes，原始碼只含密文")


if __name__ == "__main__":
    main()
