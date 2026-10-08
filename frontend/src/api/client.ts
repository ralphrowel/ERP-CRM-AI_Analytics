export interface ProblemDetails {
  type?: string
  title: string
  status: number
  detail: string
  code?: string
  instance?: string
  request_id?: string
  invalid_params?: Array<{ name: string; reason: string }>
}

export class ApiError extends Error {
  public problem: ProblemDetails

  constructor(problem: ProblemDetails) {
    super(problem.detail || problem.title || 'An API error occurred')
    this.name = 'ApiError'
    this.problem = problem
  }

  get isConflict(): boolean {
    return this.problem.status === 409 || this.problem.code === 'VERSION_CONFLICT'
  }

  get isUnauthorized(): boolean {
    return this.problem.status === 401
  }

  get isForbidden(): boolean {
    return this.problem.status === 403
  }
}

function getCsrfTokenFromCookie(): string | null {
  const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : null
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')

  const method = (options.method || 'GET').toUpperCase()
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = getCsrfTokenFromCookie()
    if (csrfToken) {
      headers.set('X-CSRF-Token', csrfToken)
    }
    if (options.body && typeof options.body === 'string' && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
    credentials: 'same-origin',
  })

  // Handle No-Content
  if (response.status === 204) {
    return {} as T
  }

  const contentType = response.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json') || contentType.includes('application/problem+json')
  const data = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    if (isJson && typeof data === 'object') {
      throw new ApiError({
        title: data.title || 'Error',
        status: response.status,
        detail: data.detail || 'Request failed',
        code: data.code,
        invalid_params: data.invalid_params,
        request_id: data.request_id,
      })
    } else {
      throw new ApiError({
        title: response.statusText || 'Error',
        status: response.status,
        detail: typeof data === 'string' ? data : 'Unknown error occurred',
      })
    }
  }

  return data as T
}

export const api = {
  get: <T>(url: string) => apiRequest<T>(url, { method: 'GET' }),
  post: <T>(url: string, body?: unknown) =>
    apiRequest<T>(url, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(url: string, body?: unknown) =>
    apiRequest<T>(url, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(url: string, body?: unknown) =>
    apiRequest<T>(url, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(url: string) => apiRequest<T>(url, { method: 'DELETE' }),
}
