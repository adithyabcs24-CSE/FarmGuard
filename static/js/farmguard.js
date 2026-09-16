/**
 * FarmGuard AI - Frontend Core Script
 * Handles authentication, API communication, crop management,
 * AI scanning, speech synthesis, and reactive dashboard state.
 */

const FarmGuard = {
  TOKEN_KEY: 'farmguard_token',
  USER_KEY: 'farmguard_user',
  THEME_KEY: 'farmguard-theme',

  // --- Theme Management ---
  initTheme() {
    const saved = localStorage.getItem(this.THEME_KEY);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (saved === 'dark' || (!saved && prefersDark)) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  },

  toggleTheme() {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem(this.THEME_KEY, isDark ? 'dark' : 'light');
  },

  // --- Auth Management ---
  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  getUser() {
    try {
      const u = localStorage.getItem(this.USER_KEY);
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  },

  setAuth(token, user) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },

  logout() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    window.location.href = '/auth?mode=login';
  },

  // --- API Client ---
  async api(endpoint, options = {}) {
    const token = this.getToken();
    const headers = options.headers || {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (!options.isFormData && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const config = {
      method: options.method || 'GET',
      headers,
      body: options.body
    };

    try {
      const res = await fetch(endpoint, config);
      if (res.status === 401) {
        // Token expired or invalid
        if (!window.location.pathname.includes('auth') && !window.location.pathname.includes('index')) {
          this.logout();
        }
      }
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.detail || `Request failed with status ${res.status}`);
      }
      return data;
    } catch (err) {
      console.error(`API error on ${endpoint}:`, err);
      throw err;
    }
  },

  // --- Toast Notifications ---
  showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:10px;';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const bg = type === 'error' ? '#dc2626' : type === 'warning' ? '#d97706' : '#15803d';
    toast.style.cssText = `background:${bg};color:#fff;padding:12px 20px;border-radius:8px;font-size:14px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.25);animation:fadeIn 0.2s ease;max-width:350px;`;
    toast.innerText = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  },

  // --- Text to Speech Audio Narration ---
  speakText(text, lang = 'English', onEnd = null) {
    if (!('speechSynthesis' in window)) {
      this.showToast('Speech synthesis not supported in this browser.', 'warning');
      if (onEnd) onEnd();
      return;
    }

    try {
      window.speechSynthesis.cancel(); // stop any ongoing speech
      if (window.speechSynthesis.paused) {
        window.speechSynthesis.resume();
      }

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95; // comfortable cadence for field listening
      utterance.pitch = 1.0;

      const l = (lang || 'English').toLowerCase();
      let targetLang = 'en-IN';
      if (l.includes('kannada') || l === 'kn' || l.includes('kn-in')) {
        targetLang = 'kn-IN';
      } else if (l.includes('hindi') || l === 'hi' || l.includes('hi-in')) {
        targetLang = 'hi-IN';
      } else if (l.includes('marathi') || l === 'mr' || l.includes('mr-in')) {
        targetLang = 'mr-IN';
      } else {
        targetLang = 'en-IN';
      }
      utterance.lang = targetLang;

      // Select matching voice if available
      const voices = window.speechSynthesis.getVoices();
      if (voices && voices.length > 0) {
        let matchingVoice = voices.find(v => v.lang.toLowerCase() === targetLang.toLowerCase());
        if (!matchingVoice) {
          matchingVoice = voices.find(v => v.lang.toLowerCase().startsWith(targetLang.split('-')[0].toLowerCase()));
        }
        if (matchingVoice) utterance.voice = matchingVoice;
      }

      if (onEnd) {
        utterance.onend = onEnd;
        utterance.onerror = onEnd;
      }

      window.speechSynthesis.speak(utterance);
      this.showToast('Playing advisory audio narration...', 'info');
    } catch (e) {
      console.warn('Speech synthesis error:', e);
      if (onEnd) onEnd();
    }
  },

  stopSpeech() {
    if ('speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch (e) {}
    }
  },

  // --- Speech-to-Text Recognition for Voice AI & Dictation ---
  isSpeechSupported() {
    return ('webkitSpeechRecognition' in window) || ('SpeechRecognition' in window);
  },

  createSpeechRecognizer({ lang = 'English', onStart, onResult, onError, onEnd }) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      return null;
    }

    let recognition;
    try {
      recognition = new SpeechRecognition();
    } catch (e) {
      console.warn('Could not instantiate SpeechRecognition:', e);
      return null;
    }

    recognition.continuous = false;
    recognition.interimResults = true;

    const l = (lang || 'English').toLowerCase();
    if (l.includes('kannada') || l === 'kn' || l.includes('kn-in')) {
      recognition.lang = 'kn-IN';
    } else if (l.includes('hindi') || l === 'hi' || l.includes('hi-in')) {
      recognition.lang = 'hi-IN';
    } else if (l.includes('marathi') || l === 'mr' || l.includes('mr-in')) {
      recognition.lang = 'mr-IN';
    } else {
      recognition.lang = 'en-IN';
    }

    if (onStart) recognition.onstart = onStart;
    if (onError) {
      recognition.onerror = (e) => {
        let msg = 'Microphone speech recognition error.';
        if (e.error === 'no-speech') {
          msg = 'No speech heard. Please tap mic and speak again.';
        } else if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
          msg = 'Microphone access is blocked. Please allow mic permission in browser.';
        } else if (e.error === 'network') {
          msg = 'Speech service network error. Please check your internet connection.';
        } else if (e.error === 'audio-capture') {
          msg = 'No microphone device was detected on your device.';
        }
        onError(e, msg);
      };
    }
    if (onEnd) recognition.onend = onEnd;

    recognition.onresult = (event) => {
      let interimTranscript = '';
      let finalTranscript = '';
      for (let i = 0; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }
      if (onResult) {
        onResult({ final: finalTranscript, interim: interimTranscript });
      }
    };

    return recognition;
  }
};

// Global init on load
document.addEventListener('DOMContentLoaded', () => {
  FarmGuard.initTheme();

  // Dynamic Navigation state
  const user = FarmGuard.getUser();
  const authNavs = document.querySelectorAll('.auth-nav-slot');
  authNavs.forEach(el => {
    if (user) {
      el.innerHTML = `
        <a href="/dashboard" class="btn btn-primary btn-sm">
          <span>Go to dashboard</span>
          <span>→</span>
        </a>
      `;
    } else {
      el.innerHTML = `
        <a href="/auth?mode=login" class="btn btn-ghost btn-sm">Login</a>
        <a href="/auth?mode=signup" class="btn btn-primary btn-sm">Get Started</a>
      `;
    }
  });

  // Theme switch buttons
  const themeBtns = document.querySelectorAll('.theme-toggle-btn');
  themeBtns.forEach(btn => {
    btn.addEventListener('click', () => FarmGuard.toggleTheme());
  });
});
