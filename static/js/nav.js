// Dynamic Navigation Header Component with Live Polling Notifications
let notificationPollInterval = null;

async function fetchNotifications() {
  const user = auth.getUser();
  if (!user) return;

  try {
    const res = await api.get("/api/notifications");
    const badge = document.getElementById("notif-badge");
    const list = document.getElementById("notif-list");

    if (badge) {
      if (res.unread_count > 0) {
        badge.textContent = res.unread_count > 9 ? "9+" : res.unread_count;
        badge.style.display = "inline-flex";
      } else {
        badge.style.display = "none";
      }
    }

    if (list) {
      if (res.notifications.length === 0) {
        list.innerHTML = `<div style="text-align:center; padding:1.5rem 0.5rem; color:var(--text-muted); font-size:0.85rem;">No notifications yet.</div>`;
      } else {
        list.innerHTML = res.notifications.map(n => `
          <div style="padding: 0.65rem; border-bottom: 1px solid var(--surface-border); font-size: 0.85rem; background: ${n.is_read ? 'transparent' : 'var(--primary-light)'}; border-radius: 4px; margin-bottom: 4px;">
            <div style="color: var(--text-main); font-weight: ${n.is_read ? '400' : '600'}; line-height: 1.35;">${n.message}</div>
            <small style="color: var(--text-muted); font-size: 0.75rem; display: block; margin-top: 3px;">
              ${new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} • ${new Date(n.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
            </small>
          </div>
        `).join("");
      }
    }
  } catch (err) {
    // Suppress network poll errors silently
  }
}

async function toggleNotificationDropdown(event) {
  event.stopPropagation();
  const dropdown = document.getElementById("notif-dropdown");
  if (!dropdown) return;

  const isVisible = dropdown.style.display === "block";
  dropdown.style.display = isVisible ? "none" : "block";

  if (!isVisible) {
    // When opened, mark notifications as read
    try {
      await api.put("/api/notifications/read", {});
      const badge = document.getElementById("notif-badge");
      if (badge) badge.style.display = "none";
    } catch (e) {
      console.warn("Could not mark notifications read:", e);
    }
  }
}

// Close dropdown on outside click
document.addEventListener("click", () => {
  const dropdown = document.getElementById("notif-dropdown");
  if (dropdown) dropdown.style.display = "none";
});

document.addEventListener("DOMContentLoaded", () => {
  const navRoot = document.getElementById("navbar-root");
  if (!navRoot) return;

  const user = auth.getUser();
  const currentPath = window.location.pathname;

  let navLinksHtml = "";

  const notifButtonHtml = `
    <li style="position: relative;">
      <button id="notif-btn" type="button" onclick="toggleNotificationDropdown(event)" class="btn btn-secondary btn-sm" style="position: relative; padding: 0.35rem 0.6rem;">
        🔔
        <span id="notif-badge" style="display: none; position: absolute; top: -6px; right: -6px; background: var(--danger); color: white; font-size: 0.7rem; font-weight: 700; min-width: 18px; height: 18px; border-radius: 9999px; align-items: center; justify-content: center; padding: 0 4px;">0</span>
      </button>

      <div id="notif-dropdown" style="display: none; position: absolute; top: 38px; right: 0; width: 330px; background: white; border: 1px solid var(--surface-border); border-radius: var(--radius-md); box-shadow: var(--shadow-lg); z-index: 1000; max-height: 400px; overflow-y: auto; padding: 0.75rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--surface-border); padding-bottom: 0.5rem; margin-bottom: 0.5rem;">
          <strong style="font-size: 0.9rem;">Notifications</strong>
          <small style="color: var(--text-muted); cursor: pointer;" onclick="fetchNotifications()">Refresh</small>
        </div>
        <div id="notif-list">
          <div style="text-align: center; padding: 1rem; color: var(--text-muted); font-size: 0.85rem;">Loading...</div>
        </div>
      </div>
    </li>
  `;

  if (!user) {
    navLinksHtml = `
      <ul class="nav-links">
        <li><a href="/index.html" class="${currentPath.endsWith("index.html") || currentPath === "/" ? "active" : ""}">Home</a></li>
        <li><a href="/customer_dashboard.html" class="${currentPath.endsWith("customer_dashboard.html") ? "active" : ""}">Find Services</a></li>
        <li><a href="/login.html" class="${currentPath.endsWith("login.html") ? "active" : ""}">Login</a></li>
        <li><a href="/register.html" class="btn btn-primary btn-sm ${currentPath.endsWith("register.html") ? "active" : ""}">Sign Up</a></li>
      </ul>
    `;
  } else if (user.role === "admin") {
    navLinksHtml = `
      <ul class="nav-links">
        <li><a href="/admin_dashboard.html" class="${currentPath.endsWith("admin_dashboard.html") ? "active" : ""}">Admin Console</a></li>
        <li><a href="/customer_dashboard.html" class="${currentPath.endsWith("customer_dashboard.html") ? "active" : ""}">Services</a></li>
        <li><a href="/admin_verification.html" class="${currentPath.endsWith("admin_verification.html") ? "active" : ""}">Verifications</a></li>
        <li><a href="/my_bookings.html" class="${currentPath.endsWith("my_bookings.html") ? "active" : ""}">Bookings</a></li>
        <li><a href="/complaints.html" class="${currentPath.endsWith("complaints.html") ? "active" : ""}">Complaints</a></li>
        ${notifButtonHtml}
        <li>
          <div class="user-badge" style="background: #fef3c7; color: #b45309;">
            <span>🛡️ ${user.name}</span>
            <small>(Admin)</small>
          </div>
        </li>
        <li><a href="javascript:void(0)" onclick="auth.logout()" class="btn btn-secondary btn-sm">Logout</a></li>
      </ul>
    `;
  } else if (user.role === "customer") {
    navLinksHtml = `
      <ul class="nav-links">
        <li><a href="/customer_dashboard.html" class="${currentPath.endsWith("customer_dashboard.html") ? "active" : ""}">Find Services</a></li>
        <li><a href="/quote_request.html" class="${currentPath.endsWith("quote_request.html") ? "active" : ""}">Request Quotes</a></li>
        <li><a href="/my_bookings.html" class="${currentPath.endsWith("my_bookings.html") ? "active" : ""}">My Bookings</a></li>
        <li><a href="/complaints.html" class="${currentPath.endsWith("complaints.html") ? "active" : ""}">Complaints</a></li>
        ${notifButtonHtml}
        <li>
          <div class="user-badge">
            <span>👤 ${user.name}</span>
            <small style="opacity:0.8">(Customer)</small>
          </div>
        </li>
        <li><a href="javascript:void(0)" onclick="auth.logout()" class="btn btn-secondary btn-sm">Logout</a></li>
      </ul>
    `;
  } else if (user.role === "provider") {
    navLinksHtml = `
      <ul class="nav-links">
        <li><a href="/provider_dashboard.html" class="${currentPath.endsWith("provider_dashboard.html") ? "active" : ""}">Dashboard</a></li>
        <li><a href="/provider_jobs.html" class="${currentPath.endsWith("provider_jobs.html") ? "active" : ""}">Jobs & Requests</a></li>
        <li><a href="/provider_profile_edit.html" class="${currentPath.endsWith("provider_profile_edit.html") ? "active" : ""}">My Profile</a></li>
        <li><a href="/complaints.html" class="${currentPath.endsWith("complaints.html") ? "active" : ""}">Complaints</a></li>
        ${notifButtonHtml}
        <li>
          <div class="user-badge">
            <span>🛠️ ${user.name}</span>
            <small style="opacity:0.8">(Provider)</small>
          </div>
        </li>
        <li><a href="javascript:void(0)" onclick="auth.logout()" class="btn btn-secondary btn-sm">Logout</a></li>
      </ul>
    `;
  }

  navRoot.innerHTML = `
    <nav class="navbar">
      <div class="nav-container">
        <a href="${user?.role === 'provider' ? '/provider_dashboard.html' : user?.role === 'admin' ? '/admin_dashboard.html' : '/customer_dashboard.html'}" class="brand">
          ⚡ <span>LocalServe</span>
        </a>
        ${navLinksHtml}
      </div>
    </nav>
  `;

  // Start live polling every 2.5 seconds if user is logged in
  if (user) {
    fetchNotifications();
    if (notificationPollInterval) clearInterval(notificationPollInterval);
    notificationPollInterval = setInterval(fetchNotifications, 2500);
  }
});
