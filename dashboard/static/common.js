function showToast(msg, type) {
    const t = document.createElement('div');
    t.className = 'toast toast-' + type;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
}

function escHtml(s) {
    if (typeof s !== 'string') return String(s || '');
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function getSettingVal(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (el.type === 'checkbox') return el.checked;
    return el.value;
}

// ---- Save bar ----

let _saveTimer = null;

function showSaving() {
    const bar = document.getElementById('saveBar');
    const st = document.getElementById('saveStatus');
    if (bar) bar.classList.add('visible');
    if (st) st.textContent = '⏳ Saving...';
}

function showSaved() {
    const st = document.getElementById('saveStatus');
    const bar = document.getElementById('saveBar');
    if (st) st.textContent = '✅ All changes saved';
    if (bar) setTimeout(() => bar.classList.remove('visible'), 2000);
}

function triggerAutoSave() {
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(saveAll, 1500);
}

// ---- Dropdown Population ----

async function populateSelect(url, selectId, selectedValue, placeholder) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    sel.innerHTML = '';
    if (placeholder) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = placeholder;
        sel.appendChild(opt);
    }
    try {
        const r = await fetch(url);
        const data = await r.json();
        data.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.name;
            if (String(item.id) === String(selectedValue)) opt.selected = true;
            sel.appendChild(opt);
        });
    } catch(e) {
        console.error('populateSelect error:', e);
    }
}

async function populateCategorySelect(url, selectId, selectedValue) {
    await populateSelect(url, selectId, selectedValue, '— None —');
}

async function populateRoleSelect(url, selectId, selectedValue) {
    await populateSelect(url, selectId, selectedValue, '— None —');
}

async function populateAllDropdowns(stats) {
    const channels = await fetch('/api/guild/channels').then(r => r.json()).catch(() => []);
    const roles = await fetch('/api/guild/roles').then(r => r.json()).catch(() => []);
    const categories = await fetch('/api/guild/categories').then(r => r.json()).catch(() => []);

    function fillSelect(selectId, items, selectedVal, placeholder) {
        const sel = document.getElementById(selectId);
        if (!sel) return;
        const prev = sel.value;
        sel.innerHTML = '';
        if (placeholder) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = placeholder;
            sel.appendChild(opt);
        }
        items.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.name;
            if (String(item.id) === String(selectedVal)) opt.selected = true;
            sel.appendChild(opt);
        });
        if (!selectedVal && prev) sel.value = prev;
    }

    fillSelect('welChannel', channels, stats.welcome_channel_id, '— Select channel —');
    fillSelect('leaveChannel', channels, stats.leave_channel_id, '— Select channel —');
    fillSelect('msgChannel', channels, null, '— Select channel —');
    fillSelect('embedChannel', channels, null, '— Select channel —');
    fillSelect('pollChannel', channels, null, '— Select channel —');
    fillSelect('panelChannel', channels, null, '— Select channel —');
    fillSelect('tktCat', categories, stats.ticket_category_id, '— None —');
    fillSelect('tktRole', roles, stats.ticket_support_role_id, '— None —');
}
