/** 触发浏览器下载（工程 JSON / 结果报告）。 */
export function downloadText(
  filename: string,
  text: string,
  mime = "text/plain;charset=utf-8",
): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** 弹出「打开文件」选择框，返回文件内容（用户取消则返回 null）。 */
export function pickTextFile(accept = ".json,application/json"): Promise<string | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.style.display = "none";
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) {
        resolve(null);
        document.body.removeChild(input);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        resolve(String(reader.result ?? ""));
        document.body.removeChild(input);
      };
      reader.onerror = () => {
        resolve(null);
        document.body.removeChild(input);
      };
      reader.readAsText(file, "utf-8");
    });
    document.body.appendChild(input);
    input.click();
  });
}
