// LocalServe Auth Helper
const auth = {
  getToken() {
    return localStorage.getItem("token");
  },

  getUser() {
    const raw = localStorage.getItem("user");
    try {
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  setAuth(token, user) {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user));
  },

  clearAuth() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
  },

  logout() {
    this.clearAuth();
    window.location.href = "/login.html";
  },

  requireAuth(allowedRoles = []) {
    const token = this.getToken();
    const user = this.getUser();

    if (!token || !user) {
      window.location.href = `/login.html?redirect=${encodeURIComponent(window.location.pathname)}`;
      return null;
    }

    if (allowedRoles.length > 0 && !allowedRoles.includes(user.role)) {
      alert(`Access denied. This page is only for ${allowedRoles.join(" / ")} accounts.`);
      if (user.role === "provider") {
        window.location.href = "/provider_dashboard.html";
      } else {
        window.location.href = "/customer_dashboard.html";
      }
      return null;
    }

    return user;
  },

  redirectIfLoggedIn() {
    const user = this.getUser();
    const token = this.getToken();
    if (token && user) {
      if (user.role === "provider") {
        window.location.href = "/provider_dashboard.html";
      } else {
        window.location.href = "/customer_dashboard.html";
      }
    }
  }
};
