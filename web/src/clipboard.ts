/** 复制到剪贴板（优先异步 API，失败时退回隐藏 textarea + execCommand）。 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 落到下面的兜底方案 */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/**
 * 读剪贴板文本（粘贴卡片要用）。
 *
 * 为什么走系统剪贴板：卡片包序列化成 JSON 写进去之后，**换个页面 / 换个浏览器**也能粘
 * （原来只存在内存 ref 里，换个标签页就没了）。
 *
 * 注意：读剪贴板需要用户手势 + 浏览器授权；失败（没权限 / 非安全上下文 / 浏览器不支持）
 * 时返回空串，调用方负责提示，并可以退回内存里那一份。
 */
export async function readText(): Promise<string> {
  try {
    if (navigator.clipboard?.readText && window.isSecureContext) {
      const text = await navigator.clipboard.readText();
      return typeof text === "string" ? text : "";
    }
  } catch {
    /* 没授权 / 不支持：交给调用方兜底 */
  }
  return "";
}
