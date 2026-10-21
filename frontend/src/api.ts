let token = sessionStorage.getItem("roadscope-token") || "";
export function setToken(value: string) {
  token = value;
  value
    ? sessionStorage.setItem("roadscope-token", value)
    : sessionStorage.removeItem("roadscope-token");
}
export const hasToken = () => Boolean(token);
export async function request<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !(options.body instanceof URLSearchParams)
  )
    headers.set("Content-Type", "application/json");
  const response = await fetch("/api" + url, { ...options, headers });
  if (!response.ok) {
    if (response.status === 401 && url != "/auth/token") {
      setToken("");
      window.dispatchEvent(new Event("session-expired"));
    }
    const body = await response
      .json()
      .catch(() => ({ detail: `Request failed (${response.status})` }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail),
    );
  }
  return response.json();
}
export async function blob(url: string) {
  const response = await fetch("/api" + url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok)
    throw new Error(
      (
        await response.json().catch(() => ({ detail: "Download failed" }))
      ).detail,
    );
  return response.blob();
}
export async function exportCSV(query: string) {
  const content = await blob("/reports/defects.csv?" + query);
  const url = URL.createObjectURL(content),
    link = document.createElement("a");
  link.href = url;
  link.download = "roadscope-defects.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
