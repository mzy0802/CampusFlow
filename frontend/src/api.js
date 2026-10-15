export async function getJson(path, options = {}) {
  const response = await fetch(`/api${path}`, { ...options, signal: AbortSignal.timeout(8000) })
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail?.message || data.detail || `请求失败 (${response.status})`)
  return data
}
