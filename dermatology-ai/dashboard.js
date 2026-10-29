// Derma-AI clinical dashboard -- extracted from dashboard.html so the page
// can be served under a strict CSP (``script-src 'self'``; no inline JS).
'use strict';
// ==================== STATE ====================
const state = {
  isAdmin: false,
  token: '',
  doctors: [],
  user: { name: '', title: '', initials: '', permissions: {} },
  patient: {
    // Intentionally empty: the previous build hard-coded a fictional patient here
    // and displayed it before any real record was loaded.
    name: '', id: '', age: '', gender: '', fitz: '', contact: '', history: '', visits: []
  },
  images: [],
  activeTab: 'visual',
  cameraActive: false,
  mediaStream: null,
  concepts: [
    // Placeholder rows. Every value is replaced with the model output returned by
    // /api/analyze before any concept is shown; nothing here is a real inference.
    { name: 'Asymmetry', key: 'asymmetry', value: 0 },
    { name: 'Border', key: 'border', value: 0 },
    { name: 'Color', key: 'color', value: 0 },
    { name: 'Diameter', key: 'diameter', value: 0 },
    { name: 'Melanin', key: 'melanin', value: 0 },
    { name: 'Inflammation', key: 'inflammation', value: 0 },
    { name: 'Ulceration', key: 'ulceration', value: 0 }
  ]
};

// ==================== AUTH HELPER ====================
async function api(url, options = {}) {
  const headers = { ...options.headers };
  if (state.token) headers['Authorization'] = 'Bearer ' + state.token;
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  return fetch(url, { ...options, headers });
}

// ==================== DOM REFS ====================
const $ = id => document.getElementById(id);

// ==== RENDER HELPERS (pure; exercised by tests/test_xss_dashboard.py) ====
const ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;', '=': '&#61;', '/': '&#47;' };
function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/[&<>"'`=\/]/g, ch => ESCAPE_MAP[ch]);
}
function safeImageUrl(url) {
  if (typeof url !== 'string') return '';
  return /^data:image\/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$/.test(url) ? url : '';
}
function renderQueueItem(p, activeId) {
  const name = p && p.name ? String(p.name) : 'Unknown';
  const initials = name.split(' ').slice(0, 2).map(w => w[0] || '').join('').toUpperCase();
  const genderAge = p && p.gender ? p.gender[0].toUpperCase() : '';
  const meta = [p.id, p.age ? p.age.split(' ')[0] + genderAge : '', p.fitz ? 'Type ' + p.fitz : ''].filter(Boolean).join(' · ');
  const active = activeId === p.id ? 'active' : '';
  const lastTag = p.visits && p.visits.length ? (p.visits[p.visits.length - 1].tag || 'routine') : 'routine';
  const status = p.status || 'active';
  const statusMap = { active: ['#3B82F6', 'In Treatment'], followup: ['#F59E0B', 'Follow Up'], consultation: ['#8B5CF6', 'Consultation'], completed: ['#10B981', 'Done'] };
  const entry = statusMap[status] || statusMap.active;
  const statusDot = entry[0], statusLabel = entry[1];
  return `<div class="queue-item ${active}" data-id="${esc(p.id)}" data-filter="${esc(lastTag)}" data-status="${esc(status)}">
      <div class="queue-avatar" style="background:linear-gradient(135deg,#8B5CF6,#6366F1);">${esc(initials) || '?'}</div>
      <div class="queue-info">
        <div class="qname">${esc(name)}</div>
        <div class="qmeta">${esc(meta)}</div>
        <div style="display:flex;align-items:center;gap:4px;margin-top:2px;"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${statusDot};"></span><span style="font-size:0.65rem;color:var(--text-muted);">${esc(statusLabel)}</span></div>
      </div>
    </div>`;
}
function renderTimelineItem(v, patientId) {
  const tagClass = ['routine', 'followup', 'urgent'].includes(v.tag) ? v.tag : 'routine';
  const desc = v.desc ? String(v.desc) : '';
  const snippet = desc.length > 80 ? desc.slice(0, 80) + '...' : desc;
  return `<div class="timeline-item" data-visit-id="${esc(v.id || '')}" data-patient-id="${esc(patientId)}">
      <div class="timeline-dot"></div>
      <div class="timeline-item-content">
        <div class="date">${esc(v.date || '')}</div>
        <div class="desc">${esc(snippet)}</div>
        <span class="tag ${tagClass}">${esc(tagClass.charAt(0).toUpperCase() + tagClass.slice(1))}</span>
      </div>
    </div>`;
}
function permissionDots(permissions) {
  return ALL_PERMISSIONS.map(p => `<span class="perm-dot ${permissions && permissions[p.key] !== false ? 'on' : 'off'}"></span>`).join('');
}
function renderDoctorRow(d) {
  const active = d.active !== false;
  return `<tr data-doctor-id="${esc(d.id)}">
      <td><input type="checkbox" class="doc-checkbox" value="${esc(d.id)}"></td>
      <td><strong>${esc(d.name)}</strong><br><span style="font-size:0.7rem;color:var(--text-muted);">${esc(d.title || '')}</span></td>
      <td>${esc(d.username)}</td>
      <td>${esc(d.email)}</td>
      <td style="font-size:0.75rem;font-family:monospace;">${esc(d.nin || '—')}</td>
      <td style="font-size:0.75rem;">${formatLoginTime(d.last_login)}</td>
      <td><span class="status-badge ${active ? 'active' : 'inactive'}">${active ? 'Active' : 'Inactive'}</span></td>
      <td style="white-space:nowrap;">${permissionDots(d.permissions)}</td>
      <td class="actions-cell">
        <button class="edit-btn" data-action="edit" data-doctor-id="${esc(d.id)}">Edit</button>
        <button class="reset-btn" data-action="reset" data-doctor-id="${esc(d.id)}">Reset</button>
        <button class="deactivate-btn" data-action="toggle" data-doctor-id="${esc(d.id)}">${active ? 'Deactivate' : 'Activate'}</button>
      </td>
    </tr>`;
}
function renderActivityItem(a) {
  const levelColors = { info: 'var(--accent)', admin: 'var(--warning)', warning: 'var(--warning)', danger: 'var(--danger)' };
  const color = levelColors[a.level] || 'var(--accent)';
  const time = a.timestamp ? new Date(a.timestamp).toLocaleString() : '';
  return `<div class="activity-item"><div class="act-dot" style="background:${color};"></div><span class="act-desc">${esc(a.event)}</span><span class="act-time" style="font-size:0.7rem;color:var(--text-muted);">${esc(time)}</span></div>`;
}
function renderSessionRow(s) {
  const name = s.name || s.username || 'Unknown';
  const role = s.role || 'doctor';
  const expires = s.expires_at ? new Date(s.expires_at).toLocaleString() : 'N/A';
  return `<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);">
      <div><strong>${esc(name)}</strong> <span style="font-size:0.7rem;color:var(--text-muted);">(${esc(role)})</span></div>
      <div style="display:flex;align-items:center;gap:8px;"><span style="font-size:0.7rem;color:var(--text-muted);">Expires: ${esc(expires)}</span><button class="reset-btn" data-action="revoke-session" data-sid="${esc(s.sid || '')}">Revoke</button></div>
    </div>`;
}
function setAvatarImage(el, url) {
  const safe = safeImageUrl(url);
  if (!el || !safe) return;
  el.innerHTML = '';
  el.style.backgroundImage = 'url("' + safe + '")';
  el.style.backgroundSize = 'cover';
  el.style.backgroundPosition = 'center';
}
function setProfilePhoto(container, url) {
  const safe = safeImageUrl(url);
  if (!container || !safe) return;
  container.textContent = '';
  const img = document.createElement('img');
  img.src = safe;
  img.alt = 'Profile Photo';
  container.appendChild(img);
}
function formatLoginTime(lastLogin) {
  if (!lastLogin) return '<span style="color:var(--text-muted);">Never</span>';
  const d = new Date(lastLogin);
  const now = new Date();
  const diff = now - d;
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
  return d.toLocaleDateString();
}

// ==== END RENDER HELPERS ====

const loginOverlay = $('loginOverlay');
const dashboard = $('dashboard');
const loginBtn = $('loginBtn');
const loginError = $('loginError');
const emailInput = $('emailInput');
const passInput = $('passInput');
const logoutBtn = $('logoutBtn');
const roleBtns = document.querySelectorAll('#roleToggle button');
const emailLabel = document.querySelector('label[for="emailInput"]');
const emailPlaceholder = emailInput ? emailInput.placeholder : '';
const enableCameraBtn = $('enableCameraBtn');
const cameraBtnText = $('cameraBtnText');
const cameraFeed = $('cameraFeed');
const cameraPreview = $('cameraPreview');
const cameraPlaceholder = $('cameraPlaceholder');
const captureBtn = $('captureBtn');
const uploadZone = $('uploadZone');
const fileInput = $('fileInput');
const thumbnails = $('thumbnails');
const imageCountBadge = $('imageCountBadge');
const timelineToggle = $('timelineToggle');
const timelineContent = $('timelineContent');
const conceptSliders = $('conceptSliders');
const conceptChart = $('conceptChart');
const triageValue = $('triageValue');
const analysisPreview = $('analysisPreview');
const analysisPlaceholder = $('analysisPlaceholder');
const bboxOverlay = $('bboxOverlay');
const notesArea = $('notesArea');
const saveNotesBtn = $('saveNotesBtn');
const clearNotesBtn = $('clearNotesBtn');
const notesSaved = $('notesSaved');

// ==================== ROLE TOGGLE ====================
roleBtns.forEach(btn => {
  btn.addEventListener('click', function() {
    roleBtns.forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    const isAdmin = this.dataset.role === 'admin';
    // Fully clear both fields and error
    emailInput.value = '';
    passInput.value = '';
    loginError.classList.remove('visible');
    loginBtn.disabled = false;
    loginBtn.classList.remove('success');
    loginBtn.querySelector('.btn-text').innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
      Secure Login
    `;
    if (isAdmin) {
      emailLabel.textContent = 'Admin Email';
      emailInput.placeholder = 'admin';
      emailInput.type = 'text';
      emailInput.autocomplete = 'off';
      passInput.autocomplete = 'off';
    } else {
      emailLabel.textContent = 'Physician Email';
      emailInput.placeholder = 'doctor@hospital.org';
      emailInput.type = 'email';
      emailInput.autocomplete = 'email';
      passInput.autocomplete = 'current-password';
    }
  });
});

// ==================== LOGIN FLOW ====================
loginBtn.addEventListener('click', async function() {
  const email = emailInput.value.trim();
  const pass = passInput.value.trim();
  loginError.classList.remove('visible');

  if (!email || !pass) {
    loginError.querySelector('span').textContent = 'Please enter both fields.';
    loginError.classList.add('visible');
    return;
  }

  const activeRole = document.querySelector('#roleToggle button.active');
  state.isAdmin = activeRole && activeRole.dataset.role === 'admin';

  this.classList.add('loading');
  this.disabled = true;

  try {
    let res;
    if (state.isAdmin) {
      res = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: email, password: pass }),
      });
      if (!res.ok) throw new Error('Invalid credentials.');
      const data = await res.json();
      state.token = data.token;
      const admin = data.admin;
      state.user.name = admin.name;
      state.user.initials = admin.name.split(' ').slice(0,2).map(w => w[0]).join('').toUpperCase();
      state.user.title = 'Administrator';
      state.user.photo = admin.photo || '';
      $('adminName').textContent = admin.name;
      $('doctorName').textContent = admin.name;
      if (state.user.photo) {
        const avatar = $('adminAvatar');
        setAvatarImage(avatar, state.user.photo);
      }
      const docInfoEl = $('doctorName').parentElement;
      const docTitleEl = docInfoEl.querySelector('.title:last-child');
      if (docTitleEl) docTitleEl.textContent = 'Clinical System Administration';
      if (typeof updateDoctorNin === 'function') updateDoctorNin('ADM-0000000001');
      loginOverlay.classList.add('hidden');
      dashboard.classList.remove('visible');
      dashboard.style.display = 'none';
      const adminDash = document.getElementById('adminDashboard');
      adminDash.style.display = 'block';
      adminDash.classList.add('visible');
      setTimeout(() => { loadDoctors(); }, 100);
    } else {
      res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pass }),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Invalid credentials.');
      }
      const data = await res.json();
      state.token = data.token;
      state.user = { ...data.physician, permissions: data.physician.permissions || {} };
      $('doctorName').textContent = state.user.name;
      if (state.user.nin && typeof updateDoctorNin === 'function') updateDoctorNin(state.user.nin);
      // Load saved profile photo
      if (state.user.photo) {
        const avatar = $('doctorAvatar');
        setAvatarImage(avatar, state.user.photo);
        const photoDiv = $('docProfilePhoto');
        setProfilePhoto(photoDiv, state.user.photo);
      }
      document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'none');
      const adminDash = document.getElementById('adminDashboard');
      adminDash.classList.remove('visible');
      adminDash.style.display = 'none';
      dashboard.style.display = '';
      loginOverlay.classList.add('hidden');
      dashboard.classList.add('visible');
      await loadPatients();
      const first = document.querySelector('.queue-item');
      if (first) loadPatientIntoForm(first.dataset.id);
    }
    this.classList.remove('loading');
    this.classList.add('success');
    this.querySelector('.btn-text').innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      Access Granted
    `;
  } catch (err) {
    this.classList.remove('loading');
    this.disabled = false;
    loginError.querySelector('span').textContent = err.message || 'Login failed.';
    loginError.classList.add('visible');
  }
});

passInput.addEventListener('keydown', e => { if (e.key === 'Enter') loginBtn.click(); });
emailInput.addEventListener('keydown', e => { if (e.key === 'Enter') passInput.focus(); });

// ==================== ACCESS CODE SHOW/HIDE ====================
$('passToggle').addEventListener('click', function() {
  const input = $('passInput');
  const svg = this.querySelector('svg');
  if (!svg) return;
  if (input.type === 'password') {
    input.type = 'text';
    this.title = 'Hide password';
    svg.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>';
  } else {
    input.type = 'password';
    this.title = 'Show password';
    svg.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
  }
});

logoutBtn.addEventListener('click', function() {
  state.token = '';
  state.isAdmin = false;
  state.user = { name: 'Dr. James Doe', title: 'Board-Certified Dermatologist', initials: 'JD', permissions: {} };
  dashboard.classList.remove('visible');
  dashboard.style.display = '';
  const adminDash = document.getElementById('adminDashboard');
  adminDash.classList.remove('visible');
  adminDash.style.display = 'none';
  loginOverlay.classList.remove('hidden');
  loginBtn.classList.remove('success');
  loginBtn.disabled = false;
  loginBtn.querySelector('.btn-text').innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
    Secure Login
  `;
  // Reset to doctor login mode
  roleBtns.forEach(b => b.classList.remove('active'));
  document.querySelector('#roleToggle button[data-role="doctor"]').classList.add('active');
  emailLabel.textContent = 'Physician Email';
  emailInput.placeholder = 'doctor@hospital.org';
  emailInput.type = 'email';
  emailInput.autocomplete = 'email';
  loginError.classList.remove('visible');
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach(t => t.stop());
    state.mediaStream = null;
    state.cameraActive = false;
    cameraFeed.classList.remove('active');
    cameraPlaceholder.classList.remove('hidden');
    enableCameraBtn.classList.remove('active');
    cameraBtnText.textContent = 'Enable Camera';
    captureBtn.disabled = true;
  }
  document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'none');
  // Reset NIN displays
  if (typeof updateDoctorNin === 'function') updateDoctorNin('—');
  // Reset profile photo displays
  ['doctorAvatar', 'adminAvatar', 'docProfilePhoto'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.innerHTML = el.id === 'adminAvatar' ? 'SA' : (el.id === 'doctorAvatar' ? 'JD' : '<span id="docProfileInitials">JD</span>');
      el.style.backgroundImage = '';
      if (el.id === 'doctorAvatar') el.style.background = 'linear-gradient(135deg, var(--accent), #6366F1)';
      if (el.id === 'adminAvatar') el.style.background = 'linear-gradient(135deg, #F59E0B, #D97706)';
    }
  });
  // Reset notif bar
  const notifBar = document.getElementById('notifBar');
  if (notifBar) notifBar.style.display = '';
  state.user.photo = null;
  state.user.nin = null;
});

// Admin logout
const adminLogoutBtn = document.getElementById('adminLogoutBtn');
if (adminLogoutBtn) adminLogoutBtn.addEventListener('click', function() {
  const adminDash = document.getElementById('adminDashboard');
  adminDash.classList.remove('visible');
  adminDash.style.display = 'none';
  logoutBtn.click();
});

// ==================== CAMERA ====================
enableCameraBtn.addEventListener('click', async function() {
  if (state.cameraActive) {
    state.mediaStream.getTracks().forEach(t => t.stop());
    state.mediaStream = null;
    state.cameraActive = false;
    cameraFeed.classList.remove('active');
    cameraPlaceholder.classList.remove('hidden');
    this.classList.remove('active');
    cameraBtnText.textContent = 'Enable Camera';
    captureBtn.disabled = true;
    enableCameraBtn.classList.remove('capture-pulse');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false
    });
    state.mediaStream = stream;
    state.cameraActive = true;
    cameraFeed.srcObject = stream;
    cameraFeed.classList.add('active');
    cameraPlaceholder.classList.add('hidden');
    this.classList.add('active');
    cameraBtnText.textContent = 'Stop Camera';
    captureBtn.disabled = false;
    enableCameraBtn.classList.add('capture-pulse');
  } catch (err) {
    if (err.name === 'NotAllowedError') {
      alert('Camera permission denied. Please allow camera access in your browser settings and try again.');
    } else if (err.name === 'NotFoundError') {
      alert('No camera device found on this system.');
    } else {
      alert('Camera error: ' + err.message);
    }
  }
});

captureBtn.addEventListener('click', function() {
  if (!state.cameraActive) return;
  const canvas = document.createElement('canvas');
  canvas.width = cameraFeed.videoWidth;
  canvas.height = cameraFeed.videoHeight;
  canvas.getContext('2d').drawImage(cameraFeed, 0, 0);
  const blob = dataURLToBlob(canvas.toDataURL('image/jpeg', 0.92));
  const file = new File([blob], `capture-${Date.now()}.jpg`, { type: 'image/jpeg' });
  addImage(file, canvas.toDataURL('image/jpeg', 0.7));
});

function dataURLToBlob(dataURL) {
  const parts = dataURL.split(',');
  const mime = parts[0].match(/:(.*?);/)[1];
  const bytes = atob(parts[1]);
  const buf = new ArrayBuffer(bytes.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) view[i] = bytes.charCodeAt(i);
  return new Blob([buf], { type: mime });
}

// ==================== DRAG & DROP ====================
uploadZone.addEventListener('click', () => fileInput.click());

uploadZone.addEventListener('dragover', e => {
  e.preventDefault();
  uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragenter', e => {
  e.preventDefault();
  uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
  uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', function(e) {
  e.preventDefault();
  this.classList.remove('dragover');
  const files = e.dataTransfer.files;
  for (const file of files) {
    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = e2 => addImage(file, e2.target.result);
      reader.readAsDataURL(file);
    }
  }
});

fileInput.addEventListener('change', function() {
  for (const file of this.files) {
    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = e => addImage(file, e.target.result);
      reader.readAsDataURL(file);
    }
  }
  this.value = '';
});

function addImage(file, src) {
  state.images.push({ file, src, id: Date.now() + Math.random() });
  renderThumbnails();
  updateDiagnostics();
  const btn = $('runDiagnosisBtn');
  btn.disabled = false;
  btn.style.opacity = '1';
  btn.style.cursor = 'pointer';
}

function removeImage(id) {
  state.images = state.images.filter(img => img.id !== id);
  renderThumbnails();
  if (state.images.length === 0) {
    resetDiagnostics();
    const btn = $('runDiagnosisBtn');
    btn.disabled = true;
    btn.style.opacity = '0.5';
  } else updateDiagnostics();
}

function renderThumbnails() {
  thumbnails.innerHTML = state.images.map(img => `
    <div class="thumbnail-item">
      <img src="${safeImageUrl(img.src)}" alt="Thumbnail">
      <button class="remove" data-id="${esc(img.id)}" title="Remove image">&times;</button>
    </div>
  `).join('');
  imageCountBadge.textContent = state.images.length + ' image' + (state.images.length !== 1 ? 's' : '');

  thumbnails.querySelectorAll('.remove').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      removeImage(parseFloat(btn.dataset.id));
    });
  });
}

// ==================== DIAGNOSTICS ====================
function updateDiagnostics() {
  if (state.images.length === 0) return;
  const img = state.images[state.images.length - 1];
  analysisPlaceholder.style.display = 'none';
  let existing = analysisPreview.querySelector('img.analysis-img');
  if (!existing) {
    existing = document.createElement('img');
    existing.className = 'analysis-img';
    existing.style.cssText = 'width:100%;height:100%;object-fit:contain;position:absolute;inset:0;';
    analysisPreview.style.position = 'relative';
    analysisPreview.insertBefore(existing, bboxOverlay);
  }
  existing.src = img.src;
  bboxOverlay.style.display = 'block';

  // No localisation head is trained on this checkpoint, so no boxes are drawn.
  // (The previous build drew three fabricated boxes with invented confidences.)
  bboxOverlay.innerHTML = '';
  bboxOverlay.style.display = 'none';

  // Update triage based on concepts
  const avg = state.concepts.reduce((s, c) => s + c.value, 0) / state.concepts.length;
  if (avg > 0.6) {
    triageValue.textContent = 'Urgent — Biopsy Recommended';
    triageValue.className = 'triage-value urgent';
  } else if (avg > 0.35) {
    triageValue.textContent = 'Follow-up — Schedule Review (2 weeks)';
    triageValue.className = 'triage-value followup';
  } else {
    triageValue.textContent = 'Routine Monitoring';
    triageValue.className = 'triage-value routine';
  }
}

function resetDiagnostics() {
  analysisPlaceholder.style.display = '';
  const img = analysisPreview.querySelector('img.analysis-img');
  if (img) img.remove();
  bboxOverlay.style.display = 'none';
  bboxOverlay.innerHTML = '';
  triageValue.textContent = 'Routine Monitoring';
  triageValue.className = 'triage-value routine';
}

// ==================== TABS ====================
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', function() {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    this.classList.add('active');
    const tabId = this.dataset.tab;
    state.activeTab = tabId;
    const tabMap = { visual: 'tabVisual', insights: 'tabInsights', notes: 'tabNotes', admin: 'tabAdmin' };
    $(tabMap[tabId]).classList.add('active');
  });
});

// ==================== TIMELINE ACCORDION ====================
timelineToggle.addEventListener('click', function() {
  this.classList.toggle('open');
  timelineContent.classList.toggle('open');
});

// ==================== CONCEPT SLIDERS & CHART ====================
function renderConceptSliders() {
  conceptSliders.innerHTML = state.concepts.map(c => `
    <div class="confidence-slider-group">
      <div class="concept-label">
        <span>${esc(c.name)}</span>
        <span class="value" id="cv-${esc(c.key)}">${(c.value * 100).toFixed(0)}%</span>
      </div>
      <input type="range" min="0" max="1" step="0.01" value="${Number(c.value) || 0}" data-key="${esc(c.key)}">
    </div>
  `).join('');

  conceptSliders.querySelectorAll('input[type="range"]').forEach(slider => {
    slider.addEventListener('input', function() {
      const key = this.dataset.key;
      const val = parseFloat(this.value);
      const concept = state.concepts.find(c => c.key === key);
      if (concept) concept.value = val;
      document.getElementById('cv-' + key).textContent = (val * 100).toFixed(0) + '%';
      renderConceptChart();
      updateTriageFromConcepts();
    });
  });
}

function renderConceptChart() {
  const maxVal = Math.max(...state.concepts.map(c => c.value), 0.01);
  conceptChart.innerHTML = state.concepts.map(c => {
    const pct = (c.value / maxVal) * 100;
    const hue = c.value > 0.6 ? 0 : c.value > 0.35 ? 38 : 160;
    return `
      <div class="concept-bar-wrap">
        <div class="concept-bar" style="height:${Math.max(pct, 4)}%;background:hsl(${hue},75%,55%);">
          <span class="bar-value">${(c.value * 100).toFixed(0)}%</span>
        </div>
        <div class="concept-bar-label">${esc(shortName(c.name))}</div>
      </div>
    `;
  }).join('');
}

function shortName(name) {
  const map = { Asymmetry: 'Asym', Border: 'Bord', Color: 'Colr', Diameter: 'Diam', Melanin: 'Mel', Inflammation: 'Inflm', Ulceration: 'Ulcr' };
  return map[name] || name.slice(0, 4);
}

function updateTriageFromConcepts() {
  const avg = state.concepts.reduce((s, c) => s + c.value, 0) / state.concepts.length;
  if (avg > 0.6) {
    triageValue.textContent = 'Urgent — Biopsy Recommended';
    triageValue.className = 'triage-value urgent';
  } else if (avg > 0.35) {
    triageValue.textContent = 'Follow-up — Schedule Review (2 weeks)';
    triageValue.className = 'triage-value followup';
  } else {
    triageValue.textContent = 'Routine Monitoring';
    triageValue.className = 'triage-value routine';
  }
}

// ==================== NOTES ====================
saveNotesBtn.addEventListener('click', async function() {
  const text = notesArea.value.trim();
  if (!text) { showToast('Please enter some notes before saving.'); return; }
  this.innerHTML = '<span class="spinner" style="display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,0.3);border-top-color:white;border-radius:50%;animation:spin 0.7s linear infinite;"></span> Saving...';
  this.disabled = true;
  const caseId = currentPatientId || 'patient-' + Date.now();
  try {
    await api('/api/notes', { method: 'POST', body: JSON.stringify({ case_id: caseId, notes: text }) });
    notesSaved.classList.add('visible');
    setTimeout(() => notesSaved.classList.remove('visible'), 3000);
  } catch (e) { showToast('Failed to save notes.'); }
  this.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save Notes';
  this.disabled = false;
});

clearNotesBtn.addEventListener('click', function() {
  if (notesArea.value.trim() && !confirm('Clear all notes?')) return;
  notesArea.value = '';
});

// ==================== SECOND OPINION BUTTON ====================
$('requestSecondOpinionBtn').addEventListener('click', function() {
  const orig = this.innerHTML;
  this.innerHTML = '<span class="spinner" style="display:inline-block;width:16px;height:16px;border:2px solid var(--text-secondary);border-top-color:var(--accent);border-radius:50%;animation:spin 0.7s linear infinite;"></span> Requesting...';
  this.disabled = true;
  setTimeout(() => {
    this.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--mint)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Request Sent to Dr. Okonkwo';
    setTimeout(() => { this.innerHTML = orig; this.disabled = false; }, 3000);
  }, 1200);
});

// ==================== ADMIN PANEL ====================
const ALL_PERMISSIONS = [
  { key: 'view_patient', label: 'View Patient' },
  { key: 'edit_patient', label: 'Edit Patient' },
  { key: 'upload_images', label: 'Upload Images' },
  { key: 'run_diagnosis', label: 'Run Diagnosis' },
  { key: 'override_triage', label: 'Override Triage' },
  { key: 'view_analytics', label: 'View Analytics' },
  { key: 'view_history', label: 'View History' },
  { key: 'export_data', label: 'Export Data' },
];

function renderPermissionsCheckbox(perms) {
  const grid = $('permissionsGrid');
  grid.innerHTML = ALL_PERMISSIONS.map(p => `
    <div class="perm-check">
      <input type="checkbox" id="perm-${p.key}" ${perms && perms[p.key] !== false ? 'checked' : ''}>
      <label for="perm-${esc(p.key)}">${esc(p.label)}</label>
    </div>
  `).join('');
}

function getPermissionsFromForm() {
  const perms = {};
  ALL_PERMISSIONS.forEach(p => {
    const cb = document.getElementById('perm-' + p.key);
    perms[p.key] = cb ? cb.checked : true;
  });
  return perms;
}

// ==================== RENDER DOCTOR TABLE ====================
function handleDoctorTableClick(event) {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const doctorId = button.dataset.doctorId;
  if (!doctorId) return;
  const action = button.dataset.action;
  if (action === 'edit') {
    openEditDoctor(doctorId);
  } else if (action === 'reset') {
    const doctor = (state.doctors || []).find(d => d.id === doctorId) || {};
    const label = doctor.username || 'this account';
    const newPassword = prompt('New password for ' + label + ':', '');
    if (newPassword) resetDoctorPassword(doctorId, newPassword);
  } else if (action === 'toggle') {
    toggleDoctorActive(doctorId);
  }
}
function renderDoctorTable(doctors) {
  const query = ($('adminSearch') || {}).value || '';
  const statusFilter = ($('adminStatusFilter') || {}).value || 'all';
  const filtered = doctors.filter(d => {
    if (statusFilter !== 'all') {
      if (statusFilter === 'active' && d.active === false) return false;
      if (statusFilter === 'inactive' && d.active !== false) return false;
    }
    if (!query) return true;
    return d.name.toLowerCase().includes(query.toLowerCase()) ||
      d.email.toLowerCase().includes(query.toLowerCase()) ||
      (d.nin || '').toLowerCase().includes(query.toLowerCase());
  });
  const tbody = $('doctorTableBody');
  if (!tbody) return;
  tbody.innerHTML = filtered.map(renderDoctorRow).join('');
  tbody.onclick = handleDoctorTableClick;
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:24px;">No doctors found.</td></tr>';
  }
  const countEl = $('adminDoctorCount');
  if (countEl) countEl.textContent = (state.doctors.length || 0) + ' doctors';
  updateBulkButtons();
}

function openAddDoctor() {
  clearFieldErrors();
  $('doctorModalTitle').textContent = 'Add Doctor';
  $('editDoctorId').value = '';
  $('docName').value = '';
  $('docUsername').value = '';
  $('docUsername').disabled = false;
  $('docEmail').value = '';
  $('docNin').value = '';
  $('docTitle').value = 'Board-Certified Dermatologist';
  $('docPassword').value = '';
  $('passwordField').style.display = '';
  $('docPassword').required = true;
  renderPermissionsCheckbox({});
  $('doctorModal').classList.add('visible');
}

function openEditDoctor(id) {
  clearFieldErrors();
  const d = state.doctors.find(d => d.id === id);
  if (!d) return;
  $('doctorModalTitle').textContent = 'Edit Doctor';
  $('editDoctorId').value = id;
  $('docName').value = d.name;
  $('docUsername').value = d.username;
  $('docUsername').disabled = true;
  $('docEmail').value = d.email;
  $('docNin').value = d.nin || '';
  $('docTitle').value = d.title || '';
  $('passwordField').style.display = 'none';
  $('docPassword').required = false;
  renderPermissionsCheckbox(d.permissions);
  $('doctorModal').classList.add('visible');
}

function closeModal() {
  $('doctorModal').classList.remove('visible');
  $('docUsername').disabled = false;
  clearFieldErrors();
  const btn = $('modalSave');
  btn.disabled = false;
  btn.textContent = 'Save Doctor';
}

// ==================== INLINE FORM ERROR HELPERS ====================
function clearFieldErrors() {
  document.querySelectorAll('#doctorForm .field-error').forEach(el => el.classList.remove('field-error'));
  document.querySelectorAll('#doctorForm .field-error-msg').forEach(el => el.remove());
  $('doctorFormError').classList.remove('visible');
}

function highlightField(fieldId, message) {
  const input = $(fieldId);
  if (!input) return;
  input.classList.add('field-error');
  input.focus();
  let msgEl = input.parentElement.querySelector('.field-error-msg');
  if (!msgEl) {
    msgEl = document.createElement('div');
    msgEl.className = 'field-error-msg';
    msgEl.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> <span></span>';
    input.parentElement.appendChild(msgEl);
  }
  msgEl.querySelector('span').textContent = message;
}

function showFormError(message) {
  const banner = $('doctorFormError');
  const text = $('doctorFormErrorText');
  if (banner && text) {
    text.textContent = message;
    banner.classList.add('visible');
  }
}

$('addDoctorBtn').addEventListener('click', openAddDoctor);
$('modalCancel').addEventListener('click', closeModal);
$('doctorModal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});

$('doctorForm').addEventListener('submit', function(e) {
  e.preventDefault();
  clearFieldErrors();

  const editId = $('editDoctorId').value;
  const payload = {
    name: $('docName').value.trim(),
    username: $('docUsername').value.trim(),
    email: $('docEmail').value.trim(),
    nin: $('docNin').value.trim(),
    title: $('docTitle').value.trim(),
    permissions: getPermissionsFromForm(),
  };
  if (!editId) payload.password = $('docPassword').value;

  // Client-side validation with inline errors
  if (!payload.name) { highlightField('docName', 'Full name is required.'); return; }
  if (!payload.username) { highlightField('docUsername', 'Username is required.'); return; }
  if (!payload.email) { highlightField('docEmail', 'Email is required.'); return; }
  if (!editId && !payload.password) { highlightField('docPassword', 'Password is required.'); return; }

  const btn = $('modalSave');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  const url = editId ? `/api/admin/doctors/${editId}` : '/api/admin/doctors';
  const method = editId ? 'PUT' : 'POST';

  api(url, { method, body: JSON.stringify(payload) })
    .then(r => {
      if (!r.ok) throw r;
      return r.json();
    })
    .then(() => {
      closeModal();
      loadDoctors();
      showToast('Doctor saved successfully.');
    })
    .catch(async (err) => {
      let msg = 'Failed to save doctor.';
      let field = null;
      try {
        if (err.json) {
          const body = await err.json();
          msg = body.detail || msg;
          field = body.field || null;
        }
      } catch (_) {
        msg = err.message || msg;
      }
      if (err.status === 401) msg = 'Session expired. Please log in again.';
      else if (err.status === 403) msg = 'Admin access required.';
      else if (err.status === 409 && field === 'username') {
        msg = 'This username is already taken.';
        highlightField('docUsername', msg);
      } else if (err.status === 409 && field === 'email') {
        msg = 'This email is already registered.';
        highlightField('docEmail', msg);
      } else if (err.status === 500) {
        msg = 'Server error. Please try again or contact support.';
        showFormError(msg);
      } else {
        showFormError(msg + ' Check all fields and try again.');
      }
      // If no field-level error was shown, show the banner
      if (!field && err.status !== 409) showFormError(msg);
    })
    .finally(() => {
      btn.disabled = false;
      btn.textContent = 'Save Doctor';
    });
});

function resetDoctorPassword(id, newPassword) {
  if (!newPassword || newPassword.length < 6) {
    alert('Password must be at least 6 characters.');
    return;
  }
  api(`/api/admin/doctors/${id}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  }).then(() => { loadDoctors(); alert('Password reset successfully.'); }).catch(() => alert('Failed to reset password.'));
}

function toggleDoctorActive(id) {
  const d = state.doctors.find(d => d.id === id);
  if (!d) return;
  const currentlyActive = d.active !== false;
  if (currentlyActive && !confirm('Deactivate this doctor? They will no longer be able to log in.')) return;
  api(`/api/admin/doctors/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ active: !currentlyActive }),
  }).then(() => loadDoctors());
}

$('adminSearch').addEventListener('input', () => renderDoctorTable(state.doctors));
$('adminStatusFilter').addEventListener('change', () => renderDoctorTable(state.doctors));
$('adminPermPreset').addEventListener('change', function() {
  const preset = this.value;
  if (!preset) return;
  // Apply permission preset to all visible doctors
  const rows = document.querySelectorAll('#doctorTable tbody tr');
  rows.forEach(row => {
    if (row.style.display === 'none') return;
    const id = row.dataset.doctorId;
    const doc = state.doctors.find(d => d.id == id);
    if (!doc) return;
    if (preset === 'full') {
      doc.permissions = Object.fromEntries(ALL_PERMISSIONS.map(p => [p.key, true]));
    } else if (preset === 'limited') {
      doc.permissions = { view_patient: true, view_history: true, view_analytics: true, upload_images: false, run_diagnosis: false, override_triage: false, edit_patient: false, export_data: false };
    } else if (preset === 'readonly') {
      doc.permissions = { view_patient: true, view_history: true, view_analytics: false, upload_images: false, run_diagnosis: false, override_triage: false, edit_patient: false, export_data: false };
    }
    // Persist to backend
    api(`/api/admin/doctors/${doc.id}/permissions`, { method: 'PUT', body: JSON.stringify({ permissions: doc.permissions }) }).catch(() => {});
  });
  renderDoctorTable(state.doctors);
  this.value = '';
});
$('refreshDoctorsBtn').addEventListener('click', loadDoctors);

// ==================== ADMIN DASHBOARD ====================
function loadActivity() {
  const logEl = $('activityLog');
  if (!logEl) return;
  const query = ($('activitySearch') || {}).value || '';
  const level = ($('activityLevelFilter') || {}).value || '';
  const params = new URLSearchParams();
  if (query) params.set('query', query);
  if (level) params.set('level', level);
  api('/api/admin/activity?' + params.toString())
    .then(r => r.json())
    .then(data => {
      const items = data.activity || [];
      logEl.innerHTML = items.length
        ? items.map(renderActivityItem).join('')
        : '<div style="text-align:center;padding:16px;color:var(--text-muted);font-size:0.8rem;">No matching activity.</div>';
    })
    .catch(() => {});
}

function revokeSessionById(sid) {
  if (!sid) return;
  if (!confirm('Revoke this session? The user will be logged out immediately.')) return;
  api(`/api/admin/sessions/${encodeURIComponent(sid)}/revoke`, { method: 'POST' })
    .then(res => {
      if (!res.ok) throw new Error('revoke failed');
      loadSessions();
    })
    .catch(() => alert('Could not revoke the session.'));
}

function loadSessions() {
  api('/api/admin/sessions')
    .then(r => r.json())
    .then(data => {
      const sessions = data.active_sessions || [];
      const el = $('sessionList');
      const countEl = $('sessionCount');
      if (countEl) countEl.textContent = sessions.length;
      if (!el) return;
      if (!sessions.length) {
        el.innerHTML = '<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:0.8rem;">No active sessions.</div>';
        return;
      }
      el.innerHTML = sessions.map(renderSessionRow).join('');
      el.querySelectorAll('button[data-action="revoke-session"]').forEach(button => {
        button.addEventListener('click', () => revokeSessionById(button.dataset.sid));
      });
    })
    .catch(() => {});
}

var _adminChartInstances = {};

function destroyAdminCharts() {
  Object.keys(_adminChartInstances).forEach(k => {
    if (_adminChartInstances[k]) _adminChartInstances[k].destroy();
  });
  _adminChartInstances = {};
}

function loadAdminCharts() {
  if (typeof Chart === 'undefined') return;
  api('/api/admin/analytics-data')
    .then(r => r.json())
    .then(data => {
      const card = $('adminChartsCard');
      if (card) card.style.display = '';
      if (typeof Chart === 'undefined') return;
      destroyAdminCharts();
      if (data.diagnosis_distribution && data.diagnosis_distribution.length) {
        _adminChartInstances.diagnosis = new Chart($('chartDiagnosis'), { type: 'doughnut', data: { labels: data.diagnosis_distribution.map(d => d.label.replace(/_/g,' ')), datasets: [{ data: data.diagnosis_distribution.map(d => d.value), backgroundColor: ['#F59E0B','#3B82F6','#10B981','#EF4444','#8B5CF6','#EC4899','#14B8A6','#F97316'] }] }, options: { responsive: true, plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 9 } } }, title: { display: true, text: 'Diagnosis', font: { size: 11 } } } } });
      }
      if (data.fitzpatrick_distribution && data.fitzpatrick_distribution.length) {
        _adminChartInstances.fitzpatrick = new Chart($('chartFitzpatrick'), { type: 'doughnut', data: { labels: data.fitzpatrick_distribution.map(d => 'Type ' + d.label), datasets: [{ data: data.fitzpatrick_distribution.map(d => d.value), backgroundColor: ['#FDE68A','#FCD34D','#D4A574','#A0764A','#6B4226','#3B1F0B'] }] }, options: { responsive: true, plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 9 } } }, title: { display: true, text: 'Fitzpatrick Type', font: { size: 11 } } } } });
      }
      if (data.triage_distribution && data.triage_distribution.length) {
        _adminChartInstances.triage = new Chart($('chartTriage'), { type: 'bar', data: { labels: data.triage_distribution.map(d => d.label), datasets: [{ label: 'Visits', data: data.triage_distribution.map(d => d.value), backgroundColor: ['#10B981','#F59E0B','#EF4444'] }] }, options: { responsive: true, plugins: { legend: { display: false }, title: { display: true, text: 'Visit Triage Tags', font: { size: 11 } } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } } });
      }
      if (data.status_distribution && data.status_distribution.length) {
        _adminChartInstances.status = new Chart($('chartStatus'), { type: 'bar', data: { labels: data.status_distribution.map(d => d.label), datasets: [{ label: 'Patients', data: data.status_distribution.map(d => d.value), backgroundColor: ['#3B82F6','#F59E0B','#8B5CF6','#10B981'] }] }, options: { responsive: true, plugins: { legend: { display: false }, title: { display: true, text: 'Patient Status', font: { size: 11 } } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } } });
      }
    })
    .catch(() => {});
}

function loadAdminStats() {
  api('/api/analytics')
    .then(r => { if (!r.ok) throw new Error(); return r.json(); })
    .then(data => {
      const m = data.metrics || {};
      $('statCases').textContent = m.total_cases || '--';
      $('statOverrides').textContent = m.override_rate != null ? Math.round(m.override_rate * 100) + '%' : '--';
    })
    .catch(() => {
      $('statCases').textContent = '--';
      $('statOverrides').textContent = '--';
    });
  const docCount = state.doctors ? state.doctors.length : 0;
  $('statDoctors').textContent = docCount;
  $('statActive').textContent = (state.doctors || []).filter(d => d.active !== false).length;
  $('adminDoctorCount').textContent = docCount + ' doctors';
}

// Bulk doctor actions
function updateBulkButtons() {
  const checked = document.querySelectorAll('.doc-checkbox:checked').length;
  $('bulkActivateBtn').disabled = checked === 0;
  $('bulkDeactivateBtn').disabled = checked === 0;
}

function getSelectedDoctorIds() {
  return Array.from(document.querySelectorAll('.doc-checkbox:checked')).map(cb => cb.value);
}

$('selectAllDoctors').addEventListener('change', function() {
  document.querySelectorAll('.doc-checkbox').forEach(cb => cb.checked = this.checked);
  updateBulkButtons();
});

$('bulkActivateBtn').addEventListener('click', function() {
  const ids = getSelectedDoctorIds();
  if (!ids.length) return;
  api('/api/admin/doctors/bulk', { method: 'POST', body: JSON.stringify({ doctor_ids: ids, active: true }) })
    .then(r => r.json()).then(() => loadDoctors()).catch(() => loadDoctors());
});

$('bulkDeactivateBtn').addEventListener('click', function() {
  const ids = getSelectedDoctorIds();
  if (!ids.length) return;
  if (!confirm('Deactivate ' + ids.length + ' doctor(s)? They will not be able to log in.')) return;
  api('/api/admin/doctors/bulk', { method: 'POST', body: JSON.stringify({ doctor_ids: ids, active: false }) })
    .then(r => r.json()).then(() => loadDoctors()).catch(() => loadDoctors());
});

// Activity log filter events
$('activitySearch').addEventListener('input', loadActivity);
$('activityLevelFilter').addEventListener('change', loadActivity);

// Change admin password
$('quickChangePassword').addEventListener('click', function() {
  $('changePasswordModal').classList.add('visible');
  $('cpCurrent').value = '';
  $('cpNew').value = '';
  $('cpConfirm').value = '';
});
$('cpCancel').addEventListener('click', function() {
  $('changePasswordModal').classList.remove('visible');
});
$('changePasswordModal').addEventListener('click', function(e) {
  if (e.target === this) this.classList.remove('visible');
});
$('changePasswordForm').addEventListener('submit', function(e) {
  e.preventDefault();
  const current = $('cpCurrent').value;
  const newPw = $('cpNew').value;
  const confirmPw = $('cpConfirm').value;
  if (newPw !== confirmPw) { alert('New passwords do not match.'); return; }
  if (newPw.length < 6) { alert('New password must be at least 6 characters.'); return; }
  api('/api/admin/change-password', { method: 'POST', body: JSON.stringify({ current_password: current, new_password: newPw }) })
    .then(r => { if (!r.ok) throw new Error(); return r.json(); })
    .then(() => { alert('Password changed successfully.'); $('changePasswordModal').classList.remove('visible'); })
    .catch(() => alert('Failed to change password. Check your current password.'));
});

// Patient CSV export
$('quickExportPatients').addEventListener('click', function() {
  const btn = this;
  btn.innerHTML = 'Exporting...';
  btn.disabled = true;
  api('/api/admin/patients/export')
    .then(r => r.blob())
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'patients.csv'; a.click();
      URL.revokeObjectURL(url);
    })
    .catch(() => alert('Export failed.'))
    .finally(() => {
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Export Patients CSV';
      btn.disabled = false;
    });
});

// Password strength validation
$('docPassword').addEventListener('input', function() {
  const val = this.value;
  const strengthEl = $('pwStrength') || (function() {
    const el = document.createElement('div');
    el.id = 'pwStrength';
    el.style.cssText = 'font-size:0.7rem;margin-top:4px;';
    document.getElementById('passwordField').appendChild(el);
    return el;
  })();
  if (!val) { strengthEl.textContent = ''; return; }
  let score = 0;
  if (val.length >= 6) score++;
  if (val.length >= 10) score++;
  if (/[A-Z]/.test(val)) score++;
  if (/[0-9]/.test(val)) score++;
  if (/[^A-Za-z0-9]/.test(val)) score++;
  const labels = ['Weak', 'Fair', 'Good', 'Strong', 'Very Strong'];
  const colors = ['#EF4444', '#F59E0B', '#3B82F6', '#10B981', '#10B981'];
  const idx = Math.min(score, 4);
  strengthEl.innerHTML = 'Strength: <span style="color:' + colors[idx] + ';font-weight:600;">' + labels[idx] + '</span>';
});

function loadDoctors() {
  const tbody = $('doctorTableBody');
  tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:24px;">Loading doctors...</td></tr>';
  api('/api/admin/doctors')
    .then(r => r.json())
    .then(data => {
      state.doctors = data.doctors || [];
      renderDoctorTable(state.doctors);
      loadAdminStats();
      loadActivity();
      loadSessions();
      loadAdminCharts();
    })
    .catch(() => {
      state.doctors = [
        { id: 'doc-001', name: 'Dr. James Doe', username: 'jdoe', email: 'j.doe@hospital.org', nin: 'NIN-9876543210', title: 'Board-Certified Dermatologist', active: true, permissions: {} },
        { id: 'doc-002', name: 'Dr. Mercy Okonkwo', username: 'mokonkwo', email: 'm.okonkwo@hospital.org', nin: 'NIN-1234567890', title: 'Senior Dermatology Resident', active: true, permissions: { export_data: false } },
      ];
      renderDoctorTable(state.doctors);
      loadAdminStats();
      loadActivity();
      loadSessions();
      loadAdminCharts();
    });
};

// Wire admin dashboard quick buttons
$('quickAddDoctor').addEventListener('click', openAddDoctor);
$('quickRefresh').addEventListener('click', function() { loadDoctors(); loadAdminStats(); loadSessions(); loadAdminCharts(); });
document.addEventListener('change', function(e) { if (e.target.classList.contains('doc-checkbox')) updateBulkButtons(); });
$('quickExport').addEventListener('click', function() {
  this.innerHTML = '<span style="display:inline-block;width:14px;height:14px;border:2px solid var(--text-secondary);border-top-color:var(--accent);border-radius:50%;animation:spin 0.7s linear infinite;"></span> Exporting...';
  this.disabled = true;
  api('/api/export')
    .then(r => {
      if (r.headers.get('content-type')?.includes('text/csv')) return r.blob().then(blob => { const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'case_history.csv'; a.click(); URL.revokeObjectURL(url); alert('Audit log exported.'); });
      return r.json().then(d => { alert('Exported: ' + (d.filename || 'OK')); });
    })
    .catch(() => { alert('Export failed.'); })
    .finally(() => {
      this.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Export Audit Log';
      this.disabled = false;
    });
});

// ==================== NOTIFICATIONS BAR ====================
let notifDismissTimer = null;

function updateNotifBar(patients) {
  const bar = document.getElementById('notifBar');
  const text = document.getElementById('notifText');
  if (!bar || !text) return;
  const followups = patients.filter(p => p.status === 'followup').length;
  const urgents = patients.filter(p => p.visits && p.visits.length && p.visits[p.visits.length-1].tag === 'urgent').length;
  const total = followups + urgents;
  if (total === 0) {
    bar.style.display = 'none';
    return;
  }
  const parts = [];
  if (followups) parts.push(`${followups} follow-up${followups > 1 ? 's' : ''} pending`);
  if (urgents) parts.push(`${urgents} urgent case${urgents > 1 ? 's' : ''} awaiting review`);
  text.textContent = '';
  const strong = document.createElement('strong');
  strong.textContent = 'Reminder: ';
  text.appendChild(strong);
  text.appendChild(document.createTextNode(parts.join(' \u2022 ')));
  bar.style.display = '';
  bar.dataset.notifData = JSON.stringify({ followups: followups > 0, urgents: urgents > 0 });
  clearTimeout(notifDismissTimer);
  notifDismissTimer = setTimeout(() => { bar.style.display = 'none'; }, 10000);
}

$('notifBar').addEventListener('click', function(e) {
  if (e.target.closest('#notifClose')) return;
  const filter = $('queueFilter');
  if (filter) {
    const data = this.dataset.notifData ? JSON.parse(this.dataset.notifData) : {};
    if (data.urgents) filter.value = 'urgent';
    else if (data.followups) filter.value = 'followup';
    else filter.value = 'all';
    filter.dispatchEvent(new Event('change'));
  }
  this.style.display = 'none';
  clearTimeout(notifDismissTimer);
});

$('notifClose').addEventListener('click', function(e) {
  e.stopPropagation();
  document.getElementById('notifBar').style.display = 'none';
  clearTimeout(notifDismissTimer);
});

// ==================== PROFILE PHOTO UPLOAD (Doctor) ====================
$('docProfileUploadBtn').addEventListener('click', function(e) {
  e.preventDefault();
  $('docProfilePhotoInput').click();
});
$('docProfilePhoto').addEventListener('click', function() {
  $('docProfilePhotoInput').click();
});
$('docProfilePhotoInput').addEventListener('change', function() {
  const file = this.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e2) {
    const dataUrl = e2.target.result;
    // Update profile photo card
    const photoDiv = $('docProfilePhoto');
    setProfilePhoto(photoDiv, dataUrl);
    // Update header avatar
    const avatar = $('doctorAvatar');
    avatar.innerHTML = '';
    avatar.style.backgroundImage = `url(${dataUrl})`;
    avatar.style.backgroundSize = 'cover';
    avatar.style.backgroundPosition = 'center';
    // Store in state
    state.user.photo = dataUrl;
    // Persist to server
    api('/api/doctors/me', {
      method: 'PUT',
      body: JSON.stringify({ photo: dataUrl }),
    }).catch(() => {});
  };
  reader.readAsDataURL(file);
  this.value = '';
});

// ==================== PROFILE PHOTO UPLOAD (Admin) ====================
$('adminAvatar').addEventListener('click', function() {
  $('adminPhotoInput').click();
});
$('adminPhotoInput').addEventListener('change', function() {
  const file = this.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e2) {
    const dataUrl = e2.target.result;
    $('adminAvatar').innerHTML = '';
    $('adminAvatar').style.backgroundImage = `url(${dataUrl})`;
    $('adminAvatar').style.backgroundSize = 'cover';
    $('adminAvatar').style.backgroundPosition = 'center';
    state.user.photo = dataUrl;
    // Persist admin photo via admin password change endpoint isn't available, store in session
  };
  reader.readAsDataURL(file);
  this.value = '';
});

// Update doctor avatar in header on login
if ($('doctorAvatar')) {
  $('doctorAvatar').addEventListener('click', function() {
    $('doctorPhotoInput').click();
  });
  $('doctorPhotoInput').addEventListener('change', function() {
    const file = this.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e2) {
      const dataUrl = e2.target.result;
      $('doctorAvatar').innerHTML = '';
      $('doctorAvatar').style.backgroundImage = `url(${dataUrl})`;
      $('doctorAvatar').style.backgroundSize = 'cover';
      $('doctorAvatar').style.backgroundPosition = 'center';
      state.user.photo = dataUrl;
      // Also update profile card
      const photoDiv = $('docProfilePhoto');
      if (photoDiv) {
        setProfilePhoto(photoDiv, dataUrl);
      }
    };
    reader.readAsDataURL(file);
    this.value = '';
  });
}

// ==================== PATIENT CRUD ====================

let currentPatientId = null;

function clearPatientForm() {
  currentPatientId = null;
  $('patientName').value = '';
  $('patientId').value = '';
  $('patientAge').value = '';
  $('patientGender').value = 'female';
  $('patientFitz').value = 'IV';
  $('patientContact').value = '';
  $('patientHistory').value = '';
  $('patientDiagnosis').value = 'melanoma';
  $('patientBodySite').value = 'upper_back';
  $('visitCount').textContent = '0 Visits';
}

function showToast(msg) {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--mint);color:#fff;padding:12px 24px;border-radius:10px;font-size:0.85rem;font-weight:500;font-family:var(--font);box-shadow:var(--shadow-lg);z-index:2000;transition:opacity 0.3s ease,transform 0.3s ease;opacity:0;pointer-events:none;';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  toast.style.transform = 'translateX(-50%) translateY(0)';
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(10px)';
  }, 2500);
}

// Queue click — show popup
$('queueList').addEventListener('click', function(e) {
  const item = e.target.closest('.queue-item');
  if (!item) return;
  showPatientPopup(item.dataset.id);
});

// Queue popup modal
const qpModal = $('queuePopupModal');
$('queuePopupCancel').addEventListener('click', function() { qpModal.classList.remove('visible'); });
$('queuePopupClose').addEventListener('click', function() { qpModal.classList.remove('visible'); });
qpModal.addEventListener('click', function(e) { if (e.target === qpModal) qpModal.classList.remove('visible'); });
$('queuePopupEdit').addEventListener('click', function() {
  qpModal.classList.remove('visible');
  const id = qpModal.dataset.patientId;
  if (id) loadPatientIntoForm(id);
});

async function showPatientPopup(id) {
  try {
    const res = await api('/api/patients/' + id);
    if (!res.ok) { showToast('Failed to load patient.'); return; }
    const data = await res.json();
    const p = data.patient;
    const visits = p.visits || [];
    const lastVisit = visits.length ? visits[visits.length-1].date + ' — ' + visits[visits.length-1].desc.slice(0, 60) : 'None';
    $('qpName').textContent = p.name || '—';
    $('qpId').textContent = p.id || '—';
    $('qpAge').textContent = p.age || '—';
    $('qpGender').textContent = p.gender || '—';
    $('qpDiagnosis').textContent = p.diagnosis || '—';
    const statusMap = { active: 'In Treatment', followup: 'Follow Up', consultation: 'Consultation', completed: 'Done' };
    $('qpStatus').textContent = statusMap[p.status] || p.status || '—';
    $('qpLastVisit').textContent = lastVisit;
    qpModal.dataset.patientId = id;
    qpModal.classList.add('visible');
  } catch (err) {
    showToast('Error loading patient.');
  }
}

// Queue filter
$('queueFilter').addEventListener('change', function() {
  const val = this.value;
  document.querySelectorAll('.queue-item').forEach(el => {
    if (val === 'all') {
      el.style.display = '';
    } else if (val === 'active_status') {
      el.style.display = el.dataset.status === 'active' ? '' : 'none';
    } else if (val === 'followup_status') {
      el.style.display = el.dataset.status === 'followup' ? '' : 'none';
    } else if (val === 'consultation_status') {
      el.style.display = el.dataset.status === 'consultation' ? '' : 'none';
    } else if (val === 'completed_status') {
      el.style.display = el.dataset.status === 'completed' ? '' : 'none';
    } else {
      el.style.display = el.dataset.filter === val ? '' : 'none';
    }
  });
});

// Queue search with debounce
let searchTimer;
$('queueSearch').addEventListener('input', function() {
  clearTimeout(searchTimer);
  const q = this.value;
  searchTimer = setTimeout(() => {
    if (q.length > 1) {
      loadPatients(q);
    } else if (q.length === 0) {
      loadPatients();
    } else {
      document.querySelectorAll('.queue-item').forEach(el => {
        const name = el.querySelector('.qname')?.textContent.toLowerCase() || '';
        el.style.display = name.includes(q.toLowerCase()) ? '' : 'none';
      });
    }
  }, 300);
});

// Save patient button
$('savePatientBtn').addEventListener('click', saveCurrentPatient);

// New patient button (clears form)
$('newPatientBtn').addEventListener('click', function() {
  clearPatientForm();
  document.querySelectorAll('.queue-item').forEach(el => el.classList.remove('active'));
});

// Delete patient button
$('deletePatientBtn').addEventListener('click', deleteCurrentPatient);

// Add patient modal
const patientModal = $('patientModal');
$('addPatientBtn').addEventListener('click', function() {
  $('newPatientName').value = '';
  $('newPatientAge').value = '';
  $('newPatientGender').value = 'female';
  $('newPatientFitz').value = 'IV';
  $('newPatientContact').value = '';
  $('newPatientHistory').value = '';
  $('newPatientDiagnosis').value = '';
  $('newPatientBodySite').value = '';
  patientModal.classList.add('visible');
});

$('patientModalCancel').addEventListener('click', function() {
  patientModal.classList.remove('visible');
});

patientModal.addEventListener('click', function(e) {
  if (e.target === patientModal) patientModal.classList.remove('visible');
});

$('patientForm').addEventListener('submit', async function(e) {
  e.preventDefault();
  const p = {
    name: $('newPatientName').value.trim(),
    age: $('newPatientAge').value.trim(),
    gender: $('newPatientGender').value,
    fitz: $('newPatientFitz').value,
    contact: $('newPatientContact').value.trim(),
    status: 'active',
    history: $('newPatientHistory').value.trim(),
    diagnosis: $('newPatientDiagnosis').value,
    body_site: $('newPatientBodySite').value,
  };
  if (!p.name) { showToast('Patient name is required.'); return; }
  try {
    const res = await api('/api/patients', {
      method: 'POST',
      body: JSON.stringify(p),
    });
    if (!res.ok) { showToast('Failed to create patient.'); return; }
    const data = await res.json();
    patientModal.classList.remove('visible');
    await loadPatients();
    await loadPatientIntoForm(data.patient.id);
    showToast('Patient added successfully.');
  } catch (e) {
    console.error('Create failed:', e);
    showToast('Error creating patient.');
  }
});

// ==================== RUN AI DIAGNOSIS ====================
$('runDiagnosisBtn').addEventListener('click', async function() {
  if (!state.images.length || !currentPatientId) { showToast('Add images and select a patient first.'); return; }
  const btn = this;
  btn.disabled = true;
  $('diagnoseBtnText').textContent = 'Diagnosing...';
  $('diagnoseSpinner').style.display = 'inline-block';
  $('diagnoseError').style.display = 'none';
  const formData = new FormData();
  formData.append('file', state.images[state.images.length - 1].file);
  const fitzMap = { I:1, II:2, III:3, IV:4, V:5, VI:6 };
  formData.append('fitzpatrick', fitzMap[$('patientFitz').value] || 4);
  try {
    const res = await api('/api/diagnose', { method: 'POST', body: formData, headers: {} });
    if (!res.ok) throw new Error('Diagnosis failed.');
    const data = await res.json();
    // Update concept sliders with real AI data (map frontend keys to backend keys)
    const CONCEPT_KEY_MAP = { asymmetry: 'asymmetry', border: 'border_irregularity', color: 'color_variegation', diameter: 'diameter_large', melanin: 'melanin_density', inflammation: 'inflammation', ulceration: 'ulceration' };
      if (data && data.concepts) {
        state.concepts.forEach(c => {
          const backendKey = CONCEPT_KEY_MAP[c.key] || c.key;
          if (data.concepts[backendKey] !== undefined) c.value = data.concepts[backendKey];
        });
      }
    renderConceptSliders();
    renderConceptChart();
    // Update triage
    const triageName = data.triage ? data.triage.replace('_', ' ') : '';
    triageValue.textContent = triageName ? (triageName.charAt(0).toUpperCase() + triageName.slice(1)) : 'Routine Monitoring';
    triageValue.className = 'triage-value ' + (data.triage_index === 2 ? 'urgent' : data.triage_index === 1 ? 'followup' : 'routine');
    // Update notes field with AI findings
    $('notesArea').value = `AI Diagnosis Results:
• Predicted class: ${data.predicted_class}
• Fitzpatrick: Type ${data.fitzpatrick} (${data.fitzpatrick_label})
• Triage: ${triageName || 'N/A'}
• Concepts: ${JSON.stringify(data.concepts || {}, null, 2)}

---\n` + $('notesArea').value;
    showToast('AI diagnosis complete.');
  } catch (err) {
    $('diagnoseError').textContent = 'Error: ' + err.message;
    $('diagnoseError').style.display = 'block';
  } finally {
    btn.disabled = false;
    $('diagnoseBtnText').textContent = 'Run AI Diagnosis';
    $('diagnoseSpinner').style.display = 'none';
  }
});

// ==================== OVERRIDE TRIAGE ====================
$('submitOverrideBtn').addEventListener('click', async function() {
  if (!currentPatientId) { showToast('Select a patient first.'); return; }
  const actionMap = { routine: 0, followup: 1, urgent: 2, emergency: 2 };
  const action = actionMap[$('notesTriageOverride').value] ?? 1;
  try {
    const res = await api('/api/override', {
      method: 'POST',
      body: JSON.stringify({ case_id: currentPatientId, clinician_action: action }),
    });
    if (!res.ok) throw new Error('Override failed.');
    showToast('Triage override submitted successfully.');
    // Also create a visit recording this override
    const vbody = {
      date: new Date().toISOString().slice(0, 10),
      desc: 'Clinician triage override — ' + $('notesTriageOverride').options[$('notesTriageOverride').selectedIndex].text,
      tag: $('notesTriageOverride').value === 'emergency' ? 'urgent' : $('notesTriageOverride').value,
      diagnosis: $('notesDiagCategory').options[$('notesDiagCategory').selectedIndex].text,
      ai_findings: '',
      treatment_notes: $('notesArea').value.slice(0, 500),
      doctor_name: state.user.name,
      lesion_location: $('patientBodySite').options[$('patientBodySite').selectedIndex].text,
    };
    await api(`/api/patients/${currentPatientId}/visits`, { method: 'POST', body: JSON.stringify(vbody) });
    loadPatientIntoForm(currentPatientId);
  } catch (err) { showToast('Error: ' + err.message); }
});

// ==================== ADD VISIT ====================
$('addVisitBtn').addEventListener('click', async function() {
  if (!currentPatientId) { showToast('Select a patient first.'); return; }
  const actionMap = { routine: 0, followup: 1, urgent: 2, emergency: 2 };
  const tag = $('notesTriageOverride').value === 'emergency' ? 'urgent' : $('notesTriageOverride').value;
  const vbody = {
    date: new Date().toISOString().slice(0, 10),
    desc: $('notesArea').value.split('\n')[0].slice(0, 200) || 'Clinical visit',
    tag: tag,
    diagnosis: $('notesDiagCategory').options[$('notesDiagCategory').selectedIndex].text,
    ai_findings: state.concepts.map(c => `${c.name}: ${(c.value * 100).toFixed(0)}%`).join(', '),
    treatment_notes: $('notesArea').value.slice(0, 1000),
    doctor_name: state.user.name,
    lesion_location: $('patientBodySite').options[$('patientBodySite').selectedIndex].text,
  };
  try {
    const res = await api(`/api/patients/${currentPatientId}/visits`, { method: 'POST', body: JSON.stringify(vbody) });
    if (!res.ok) throw new Error('Failed to record visit.');
    // Save notes too
    await api('/api/notes', { method: 'POST', body: JSON.stringify({ case_id: currentPatientId, notes: $('notesArea').value }) });
    showToast('Visit recorded and notes saved.');
    loadPatientIntoForm(currentPatientId);
  } catch (err) { showToast('Error: ' + err.message); }
});

// ==================== OFFLINE UPDATE ====================
$('runOfflineUpdateBtn').addEventListener('click', async function() {
  const btn = this;
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="display:inline-block;width:14px;height:14px;border:2px solid rgba(0,0,0,0.15);border-top-color:var(--mint);border-radius:50%;animation:spin 0.6s linear infinite;margin-right:6px;"></div>Updating...';
  try {
    const res = await api('/api/offline-update', { method: 'POST' });
    const data = await res.json();
    $('systemActionMsg').style.display = 'block';
    $('systemActionMsg').style.background = data.status === 'completed' ? 'var(--mint-light)' : '#FEF3C7';
    $('systemActionMsg').style.color = data.status === 'completed' ? '#065F46' : '#92400E';
    $('systemActionMsg').textContent = data.status === 'completed' ? `Offline update complete. Policy loss: ${data.policy_loss}, Buffer: ${data.buffer_size}` : data.message || 'Update completed.';
  } catch (err) { showToast('Error: ' + err.message); }
  finally { btn.disabled = false; btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg> Run Offline Update'; }
});

// ==================== EXPORT DATA ====================
$('exportDataBtn').addEventListener('click', async function() {
  try {
    const res = await api('/api/export');
    if (res.headers.get('content-type')?.includes('text/csv')) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'case_history.csv'; a.click();
      URL.revokeObjectURL(url);
      showToast('Data exported successfully.');
    } else {
      const data = await res.json();
      showToast(data.status === 'exported' ? 'Data exported.' : 'Export failed.');
    }
  } catch (err) { showToast('Error: ' + err.message); }
});

// ==================== PATIENT CRUD (with auth) ====================

async function loadPatients() {
  try {
    const res = await api('/api/patients' + (arguments[0] ? '?query=' + encodeURIComponent(arguments[0]) : ''));
    const data = await res.json();
    const patients = data.patients || [];
    const list = $('queueList');
    list.innerHTML = patients.map(p => renderQueueItem(p, currentPatientId)).join('');
    $('queueCount').textContent = patients.length + ' patient' + (patients.length !== 1 ? 's' : '');
    updateNotifBar(patients);
  } catch (e) { console.error('Failed to load patients:', e); }
}

async function loadPatientIntoForm(patientId) {
  try {
    const res = await api(`/api/patients/${patientId}`);
    if (!res.ok) return;
    const data = await res.json();
    const p = data.patient;
    currentPatientId = p.id;
    state.patient = p;
    $('patientName').value = p.name || '';
    $('patientId').value = p.id || '';
    $('patientAge').value = p.age || '';
    $('patientGender').value = p.gender || 'female';
    $('patientFitz').value = p.fitz || 'IV';
    $('patientContact').value = p.contact || '';
    $('patientStatus').value = p.status || 'active';
    $('patientHistory').value = p.history || '';
    $('patientDiagnosis').value = p.diagnosis || 'melanoma';
    $('patientBodySite').value = p.body_site || 'upper_back';
    $('visitCount').textContent = (p.visits ? p.visits.length : 0) + ' Visits';
    const timelineInner = document.querySelector('.timeline-inner');
    if (timelineInner) {
      if (p.visits && p.visits.length) {
        timelineInner.innerHTML = p.visits.map(v => renderTimelineItem(v, p.id)).join('');
      } else {
        timelineInner.innerHTML = '<div style="text-align:center;padding:20px 0;color:var(--text-muted);font-size:0.85rem;">No visit history recorded for this patient.</div>';
      }
    }
    document.querySelectorAll('.queue-item').forEach(el => el.classList.toggle('active', el.dataset.id === p.id));
    try {
      const notesRes = await api(`/api/notes/${p.id}`);
      const notesData = await notesRes.json();
      if (notesData.notes) $('notesArea').value = notesData.notes;
    } catch(e) {}
  } catch (e) { console.error('Failed to load patient:', e); }
}

async function saveCurrentPatient() {
  const p = {
    name: $('patientName').value.trim(),
    id: $('patientId').value.trim(),
    age: $('patientAge').value.trim(),
    gender: $('patientGender').value,
    fitz: $('patientFitz').value,
    contact: $('patientContact').value.trim(),
    status: $('patientStatus').value,
    history: $('patientHistory').value.trim(),
    diagnosis: $('patientDiagnosis').value,
    body_site: $('patientBodySite').value,
  };
  if (!p.name) { showToast('Patient name is required.'); return; }
  try {
    if (currentPatientId) {
      const res = await api(`/api/patients/${currentPatientId}`, { method: 'PUT', body: JSON.stringify(p) });
      if (!res.ok) { showToast('Failed to save patient.'); return; }
    } else {
      const res = await api('/api/patients', { method: 'POST', body: JSON.stringify(p) });
      if (!res.ok) { showToast('Failed to create patient.'); return; }
      const data = await res.json();
      currentPatientId = data.patient.id;
      $('patientId').value = data.patient.id;
    }
    await loadPatients();
    if (currentPatientId) {
      await loadPatientIntoForm(currentPatientId);
    }
    showToast('Patient saved successfully.');
  } catch (e) { showToast('Error saving patient.'); }
}

async function deleteCurrentPatient() {
  if (!currentPatientId) return;
  const name = state.patient.name || 'this patient';
  if (!confirm(`Are you sure you want to delete ${name}? This cannot be undone.`)) return;
  try {
    const res = await api(`/api/patients/${currentPatientId}`, { method: 'DELETE' });
    if (!res.ok) { showToast('Failed to delete patient.'); return; }
    currentPatientId = null;
    clearPatientForm();
    await loadPatients();
    showToast('Patient deleted.');
  } catch (e) { showToast('Error deleting patient.'); }
}

// ==================== FORM VALIDATION ====================
document.querySelectorAll('#patientCard input, #patientCard textarea').forEach(el => {
  el.addEventListener('blur', function() {
    if (this.hasAttribute('required') && !this.value.trim()) {
      this.style.borderColor = 'var(--danger)';
    } else {
      this.style.borderColor = '';
    }
  });
});

// ==================== VISIT HISTORY CLICK ====================
const visitModal = $('visitModal');

document.getElementById('timelineContent').addEventListener('click', async function(e) {
  const item = e.target.closest('.timeline-item');
  if (!item) return;
  const visitId = item.dataset.visitId;
  const patientId = item.dataset.patientId;
  if (!visitId || !patientId) {
    // Fallback: show static data from DOM
    const dateEl = item.querySelector('.date');
    const descEl = item.querySelector('.desc');
    const tagEl2 = item.querySelector('.tag');
    $('visitModalDate').textContent = dateEl ? dateEl.textContent : '';
    $('visitDetailDesc').textContent = descEl ? descEl.textContent : '—';
    const t = tagEl2 ? tagEl2.textContent : 'Routine';
    $('visitDetailTag').textContent = t;
    $('visitDetailTag').className = 'tag ' + (tagEl2 ? tagEl2.className.replace('tag ', '') : 'routine');
    $('visitDetailDiagnosis').textContent = 'Not available';
    $('visitDetailDoctor').textContent = '—';
    $('visitDetailLocation').textContent = '—';
    $('visitDetailSize').textContent = '—';
    $('visitDetailAI').textContent = 'Detailed AI findings not available for this visit.';
    $('visitDetailTreatment').textContent = 'Detailed treatment notes not available for this visit.';
    visitModal.classList.add('visible');
    return;
  }
  try {
    const res = await api(`/api/patients/${patientId}/visits/${visitId}`);
    if (!res.ok) return;
    const data = await res.json();
    const v = data.visit;
    $('visitModalDate').textContent = v.date || '';
    $('visitDetailDesc').textContent = v.desc || '—';
    const tagEl = $('visitDetailTag');
    const tagClass = v.tag || 'routine';
    tagEl.textContent = (tagClass.charAt(0).toUpperCase() + tagClass.slice(1));
    tagEl.className = 'tag ' + tagClass;
    $('visitDetailDiagnosis').textContent = v.diagnosis || '—';
    $('visitDetailDoctor').textContent = v.doctor_name || '—';
    $('visitDetailLocation').textContent = v.lesion_location || '—';
    $('visitDetailSize').textContent = v.lesion_size || '—';
    $('visitDetailAI').textContent = v.ai_findings || 'No AI findings recorded.';
    $('visitDetailTreatment').textContent = v.treatment_notes || 'No treatment notes.';
    visitModal.classList.add('visible');
  } catch (err) {
    console.error('Failed to load visit:', err);
  }
});

$('visitModalClose').addEventListener('click', function() {
  visitModal.classList.remove('visible');
});

visitModal.addEventListener('click', function(e) {
  if (e.target === visitModal) visitModal.classList.remove('visible');
});

// ==================== UPDATE DOCTOR NIN DISPLAY ====================
function updateDoctorNin(nin) {
  const display = $('doctorNinDisplay');
  if (display) display.textContent = 'NIN: ' + (nin || '—');
  const adminNin = $('adminNinDisplay');
  if (adminNin) adminNin.textContent = 'NIN: ' + (nin || 'ADM-0000000001');
  const profileNin = $('docProfileNin');
  if (profileNin) profileNin.textContent = nin || '—';
}
// Call on login
// (will be called from login flow)

// ==================== INIT ====================
renderConceptSliders();
renderConceptChart();
