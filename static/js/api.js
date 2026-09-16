// LocalServe REST API Client
const API_BASE = "";

async function apiFetch(endpoint, options = {}) {
  const token = localStorage.getItem("token");
  const headers = {
    Accept: "application/json",
    ...(options.headers || {})
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers
  });

  // Handle 401 Unauthorized (Expired or invalid token)
  if (response.status === 401 && !endpoint.includes("/api/auth/login")) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    // Only redirect if not on public landing or login/register pages
    const path = window.location.pathname;
    if (!path.endsWith("login.html") && !path.endsWith("register.html") && !path.endsWith("index.html") && path !== "/") {
      window.location.href = "/login.html?expired=true";
      return;
    }
  }

  let data = null;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const errorMsg = (data && data.detail) ? data.detail : `Request failed with status ${response.status}`;
    const error = new Error(errorMsg);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

const api = {
  get: (endpoint) => apiFetch(endpoint, { method: "GET" }),
  post: (endpoint, body) => apiFetch(endpoint, { method: "POST", body }),
  put: (endpoint, body) => apiFetch(endpoint, { method: "PUT", body }),
  delete: (endpoint) => apiFetch(endpoint, { method: "DELETE" })
};
