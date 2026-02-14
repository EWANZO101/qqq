// ===== Tab Switching =====
function switchTab(name) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.remove('bg-primary-600', 'text-white');
        b.classList.add('text-gray-400', 'hover:text-white', 'hover:bg-white/5');
    });
    var panel = document.getElementById('panel-' + name);
    if (panel) panel.classList.remove('hidden');
    var btn = document.getElementById('tab-' + name);
    if (btn) {
        btn.classList.add('bg-primary-600', 'text-white');
        btn.classList.remove('text-gray-400', 'hover:text-white', 'hover:bg-white/5');
    }
    if (name === 'playtime') fetchPlaytime();
    if (name === 'stats') fetchStats();
    if (name === 'character') fetchCharacter();
    window.location.hash = name;
}

// ===== Helpers =====
function fmt(m) {
    if (!m) return '0m';
    var d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mn = m % 60;
    var p = [];
    if (d > 0) p.push(d + 'd');
    if (h > 0) p.push(h + 'h');
    if (mn > 0 || !p.length) p.push(mn + 'm');
    return p.join(' ');
}

function timeAgo(iso) {
    var d = new Date(iso);
    var s = Math.floor((Date.now() - d) / 1000);
    if (s < 60) return 'Just now';
    if (s < 3600) return Math.floor(s / 60) + 'm ago';
    if (s < 86400) return Math.floor(s / 3600) + 'h ago';
    return Math.floor(s / 86400) + 'd ago';
}

function money(n) {
    return '$' + Number(n || 0).toLocaleString();
}

// ===== PLAYTIME =====
function fetchPlaytime() {
    fetch('/api/playtime').then(function(r) { return r.json(); }).then(function(d) {
        if (d.error) {
            document.getElementById('status-text').textContent = 'Could not load data';
            return;
        }
        if (d.is_online) {
            document.getElementById('status-dot').className = 'w-3 h-3 rounded-full bg-green-500 animate-pulse';
            document.getElementById('status-text').textContent = 'You are currently in-game';
            document.getElementById('status-text').className = 'text-green-400 text-sm font-medium';
            document.getElementById('player-session').textContent = 'Session: ' + fmt(d.current_session_minutes);
            document.getElementById('sidebar-status').textContent = 'Online';
            document.getElementById('sidebar-status').className = 'text-green-400 text-xs font-medium';
        } else {
            document.getElementById('status-dot').className = 'w-3 h-3 rounded-full bg-gray-500';
            document.getElementById('status-text').textContent = 'You are not currently in-game';
            document.getElementById('sidebar-status').textContent = 'Offline';
            document.getElementById('sidebar-status').className = 'text-gray-500 text-xs';
        }
        document.getElementById('pt-session').textContent = d.is_online ? fmt(d.current_session_minutes) : 'N/A';
        document.getElementById('pt-today').textContent = fmt(d.today_minutes);
        document.getElementById('pt-week').textContent = fmt(d.week_minutes);
        document.getElementById('pt-month').textContent = fmt(d.month_minutes);
        document.getElementById('pt-year').textContent = fmt(d.year_minutes);
        document.getElementById('pt-total').textContent = fmt(d.total_minutes);
        document.getElementById('pt-lastseen').textContent = d.last_seen ? new Date(d.last_seen).toLocaleString() : 'Never';
    }).catch(function() {});
    
    // Load session history
    fetchSessionHistory();
}

var categoryColors = {
    'quit': {bg:'bg-green-500/20', text:'text-green-400', label:'Quit'},
    'timeout': {bg:'bg-yellow-500/20', text:'text-yellow-400', label:'Timeout'},
    'crash': {bg:'bg-red-500/20', text:'text-red-400', label:'Crash'},
    'kicked': {bg:'bg-purple-500/20', text:'text-purple-400', label:'Kicked'},
    'banned': {bg:'bg-red-500/20', text:'text-red-400', label:'Banned'},
    'connection': {bg:'bg-orange-500/20', text:'text-orange-400', label:'Network'},
    'server': {bg:'bg-blue-500/20', text:'text-blue-400', label:'Server'},
    'switch': {bg:'bg-cyan-500/20', text:'text-cyan-400', label:'Switched'},
    'other': {bg:'bg-gray-500/20', text:'text-gray-400', label:'Other'}
};

function fetchSessionHistory() {
    fetch('/api/player/session-history?limit=30').then(function(r) { return r.json(); }).then(function(d) {
        // Category badges
        var catEl = document.getElementById('session-categories');
        if (catEl && d.categories) {
            catEl.innerHTML = '';
            for (var cat in d.categories) {
                var c = categoryColors[cat] || categoryColors['other'];
                catEl.innerHTML += '<span class="inline-flex items-center px-2 py-1 rounded-md text-xs ' + c.bg + ' ' + c.text + '">' + c.label + ': ' + d.categories[cat] + '</span>';
            }
        }
        
        var el = document.getElementById('session-history');
        if (!el) return;
        if (!d.sessions || d.sessions.length === 0) {
            el.innerHTML = '<p class="text-gray-600 text-sm">No session history yet</p>';
            return;
        }
        el.innerHTML = '';
        d.sessions.forEach(function(s) {
            var c = categoryColors[s.category] || categoryColors['other'];
            var div = document.createElement('div');
            div.className = 'flex items-center justify-between py-3 px-4 bg-surface-800/50 rounded-lg';
            
            var startTime = new Date(s.session_start);
            var endTime = new Date(s.session_end);
            var dateStr = startTime.toLocaleDateString([], {month:'short', day:'numeric'});
            var timeStr = startTime.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) + ' - ' + endTime.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
            var pingHtml = s.ping ? ' <span class="text-gray-600">• ' + s.ping + 'ms</span>' : '';
            
            div.innerHTML = '<div class="flex items-center space-x-3 flex-1 min-w-0">' +
                '<span class="inline-flex items-center px-2 py-1 rounded-md text-xs font-bold uppercase ' + c.bg + ' ' + c.text + ' flex-shrink-0">' + c.label + '</span>' +
                '<div class="min-w-0">' +
                    '<div class="text-white text-sm truncate" title="' + (s.reason || '') + '">' + (s.reason || 'Unknown') + pingHtml + '</div>' +
                    '<div class="text-gray-500 text-xs">' + dateStr + ' • ' + timeStr + '</div>' +
                '</div>' +
            '</div>' +
            '<span class="text-gray-400 text-sm font-semibold whitespace-nowrap ml-3">' + fmt(s.minutes) + '</span>';
            el.appendChild(div);
        });
    }).catch(function() {});
}

// ===== STATS =====
function fetchStats() {
    fetch('/api/stats').then(function(r) { return r.json(); }).then(function(d) {
        if (d.error) return;
        document.getElementById('st-kills').textContent = d.total_kills;
        document.getElementById('st-deaths').textContent = d.total_deaths;
        document.getElementById('st-kd').textContent = d.kd_ratio;
        document.getElementById('sidebar-kd').textContent = d.kd_ratio;

        document.getElementById('st-today-k').textContent = d.today_kills;
        document.getElementById('st-today-d').textContent = d.today_deaths;
        document.getElementById('st-week-k').textContent = d.week_kills;
        document.getElementById('st-week-d').textContent = d.week_deaths;
        document.getElementById('st-month-k').textContent = d.month_kills;
        document.getElementById('st-month-d').textContent = d.month_deaths;

        // Top weapons
        var wEl = document.getElementById('st-weapons');
        if (d.top_weapons && d.top_weapons.length > 0) {
            wEl.innerHTML = '';
            d.top_weapons.forEach(function(w) {
                var div = document.createElement('div');
                div.className = 'flex items-center justify-between';
                div.innerHTML = '<span class="text-gray-300">' + w.weapon + '</span><span class="text-red-400 font-semibold">' + w.count + '</span>';
                wEl.appendChild(div);
            });
        }

        // Top death causes
        var cEl = document.getElementById('st-causes');
        if (d.top_death_causes && d.top_death_causes.length > 0) {
            cEl.innerHTML = '';
            d.top_death_causes.forEach(function(c) {
                var div = document.createElement('div');
                div.className = 'flex items-center justify-between';
                div.innerHTML = '<span class="text-gray-300">' + c.cause + '</span><span class="text-gray-400 font-semibold">' + c.count + '</span>';
                cEl.appendChild(div);
            });
        }

        // Recent events
        var rEl = document.getElementById('st-recent');
        if (d.recent_events && d.recent_events.length > 0) {
            rEl.innerHTML = '';
            d.recent_events.forEach(function(e) {
                var div = document.createElement('div');
                div.className = 'flex items-center justify-between py-2 border-b border-white/5';
                var icon, text, color;
                if (e.type === 'kill') {
                    icon = '🔫';
                    color = 'text-red-400';
                    text = 'Killed <span class="text-white">' + (e.victim || 'Unknown') + '</span> with ' + (e.weapon || 'Unknown');
                } else {
                    icon = '💀';
                    color = 'text-gray-400';
                    if (e.killer) {
                        text = 'Killed by <span class="text-white">' + e.killer + '</span> with ' + (e.weapon || 'Unknown');
                    } else {
                        text = 'Died from <span class="text-white">' + (e.cause || e.weapon || 'Unknown') + '</span>';
                    }
                }
                div.innerHTML = '<div class="flex items-center space-x-2"><span>' + icon + '</span><span class="' + color + ' text-xs">' + text + '</span></div><span class="text-gray-600 text-xs whitespace-nowrap">' + timeAgo(e.time) + '</span>';
                rEl.appendChild(div);
            });
        }
    }).catch(function() {});
}

// ===== CHARACTER =====
function fetchCharacter() {
    var loading = document.getElementById('char-loading');
    var container = document.getElementById('char-container');
    if (!loading || !container) return;

    loading.classList.remove('hidden');
    container.classList.add('hidden');

    fetch('/api/player-info').then(function(r) { return r.json(); }).then(function(d) {
        loading.classList.add('hidden');
        container.classList.remove('hidden');

        if (d.error) {
            container.innerHTML = '<div class="glass-card rounded-2xl p-8 text-center"><p class="text-gray-400">' + d.error + '</p></div>';
            return;
        }

        if (!d.characters || d.characters.length === 0) {
            container.innerHTML = '<div class="glass-card rounded-2xl p-8 text-center"><p class="text-gray-400">No characters found</p></div>';
            return;
        }

        container.innerHTML = '';
        d.characters.forEach(function(c, i) {
            var genderIcon = c.gender === 0 ? '👨' : '👩';
            var jobBadge = c.job_label !== 'Unemployed' ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-900/50 text-blue-300 border border-blue-500/30">' + c.job_label + (c.job_grade ? ' - ' + c.job_grade : '') + '</span>' : '<span class="text-gray-500 text-xs">Unemployed</span>';
            var gangBadge = c.gang_name !== 'none' ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-900/50 text-red-300 border border-red-500/30">' + c.gang_label + '</span>' : '';
            var jailBadge = c.in_jail > 0 ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-900/50 text-orange-300 border border-orange-500/30">In Jail: ' + c.in_jail + ' months</span>' : '';
            var deadBadge = c.is_dead ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-900/50 text-red-300 border border-red-500/30">DEAD</span>' : '';
            var recordBadge = c.has_record ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-900/50 text-yellow-300 border border-yellow-500/30">Criminal Record</span>' : '';

            var licenses = '';
            if (c.licenses) {
                Object.keys(c.licenses).forEach(function(k) {
                    if (c.licenses[k]) {
                        licenses += '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-green-900/30 text-green-400 border border-green-500/20 mr-1 mb-1">' + k + '</span>';
                    }
                });
            }

            var card = document.createElement('div');
            card.className = 'glass-card rounded-2xl p-6';
            card.innerHTML = '<div class="flex items-start justify-between mb-4">' +
                '<div>' +
                    '<h3 class="text-lg font-semibold text-white">' + genderIcon + ' ' + c.firstname + ' ' + c.lastname + '</h3>' +
                    '<p class="text-gray-500 text-xs">CID: ' + c.citizenid + ' | ' + c.blood_type + ' | DOB: ' + (c.birthdate || 'N/A') + '</p>' +
                '</div>' +
                '<div class="flex flex-wrap gap-1">' + jobBadge + gangBadge + jailBadge + deadBadge + recordBadge + '</div>' +
            '</div>' +
            '<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">' +
                '<div class="bg-surface-800/50 rounded-lg p-3 text-center"><div class="text-xs text-gray-500">Cash</div><div class="text-green-400 font-semibold">' + money(c.cash) + '</div></div>' +
                '<div class="bg-surface-800/50 rounded-lg p-3 text-center"><div class="text-xs text-gray-500">Bank</div><div class="text-blue-400 font-semibold">' + money(c.bank) + '</div></div>' +
                '<div class="bg-surface-800/50 rounded-lg p-3 text-center"><div class="text-xs text-gray-500">Health</div><div class="text-red-400 font-semibold">' + c.health + '</div></div>' +
                '<div class="bg-surface-800/50 rounded-lg p-3 text-center"><div class="text-xs text-gray-500">Armor</div><div class="text-blue-300 font-semibold">' + c.armor + '</div></div>' +
            '</div>' +
            '<div class="grid grid-cols-3 gap-3 mb-4">' +
                '<div class="bg-surface-800/50 rounded-lg p-3 text-center"><div class="text-xs text-gray-500">Hunger</div><div class="text-orange-400 font-semibold">' + c.hunger + '%</div></div>' +
                '<div class="bg-surface-800/50 rounded-lg p-3 text-center"><div class="text-xs text-gray-500">Thirst</div><div class="text-cyan-400 font-semibold">' + c.thirst + '%</div></div>' +
                '<div class="bg-surface-800/50 rounded-lg p-3 text-center"><div class="text-xs text-gray-500">Stress</div><div class="text-purple-400 font-semibold">' + c.stress + '%</div></div>' +
            '</div>' +
            (licenses ? '<div class="mb-3"><span class="text-xs text-gray-500 mr-2">Licenses:</span>' + licenses + '</div>' : '') +
            '<div class="text-xs text-gray-600">Last updated: ' + (c.last_updated ? new Date(c.last_updated).toLocaleString() : 'N/A') + '</div>';
            container.appendChild(card);
        });
    }).catch(function() {
        loading.classList.add('hidden');
        container.classList.remove('hidden');
        container.innerHTML = '<div class="glass-card rounded-2xl p-8 text-center"><p class="text-red-400">Failed to load character data</p></div>';
    });
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', function() {
    var hash = window.location.hash.replace('#', '');
    if (['profile', 'stats', 'playtime', 'character', 'password'].includes(hash)) {
        switchTab(hash);
    }
    setInterval(function() {
        var pt = document.getElementById('panel-playtime');
        if (pt && !pt.classList.contains('hidden')) fetchPlaytime();
    }, 60000);
});
