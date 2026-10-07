document.addEventListener('DOMContentLoaded', () => {
    // Unique session ID per browser tab to guarantee strict multi-tab & multi-account isolation
    const tabSessionId = 'tab_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);

    // DOM Elements
    const validateBtn = document.getElementById('validate-btn');
    const scanBtn = document.getElementById('scan-btn');
    const migrateBtn = document.getElementById('migrate-btn');
    const downloadReportBtn = document.getElementById('download-report-btn');
    const downloadMigReportBtn = document.getElementById('download-mig-report-btn');
    const folderFilter = document.getElementById('folder-filter');
    const dependencyTree = document.getElementById('dependency-tree');
    const scanResults = document.getElementById('scan-results');
    const consoleSection = document.getElementById('console-section');
    const terminalLog = document.getElementById('terminal-log');
    const reportSummaryBody = document.getElementById('report-summary-body');
    const overallStatus = document.getElementById('overall-status');
    const toast = document.getElementById('toast-notification');

    // Tab 2: Migration Agent DOM Elements
    const migrateProcessSearch = document.getElementById('migrate-process-search');
    const migrateSearchClear = document.getElementById('migrate-search-clear');
    const migrateSelectionCount = document.getElementById('migrate-selection-count');
    const migrateSelectAllBtn = document.getElementById('migrate-select-all-btn');
    const migrateClearAllBtn = document.getElementById('migrate-clear-all-btn');
    const migrateProcessTree = document.getElementById('migrate-process-tree');
    const migrationModeBadge = document.getElementById('migration-mode-badge');
    const migrationIntentNote = document.getElementById('migration-intent-note');
    const selectedProcessIds = new Set();
    const selectedConnectionIds = new Set();
    const selectedOperationIds = new Set();
    const selectedProfileIds = new Set();
    const selectedMapIds = new Set();
    const selectedCacheIds = new Set();
    let migrateTypeFilter = 'all';
    
    // Credentials fields
    const usernameInput = document.getElementById('boomi-username');
    const tokenInput = document.getElementById('boomi-token');
    const accountInput = document.getElementById('boomi-account');
    const branchInput = document.getElementById('boomi-branch');
    const urlInput = document.getElementById('boomi-url');
    
    // AI fields
    const providerInput = document.getElementById('ai-provider');
    const keyInput = document.getElementById('ai-key');

    // Navigation Tabs
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    
    // Enabled navigation tabs tracking
    const navTabs = {
        scan: document.querySelector('[data-tab="scan-tab"]'),
        migrate: document.getElementById('migrate-nav-tab'),
        report: document.getElementById('report-nav-tab')
    };

    // Helper: Show toast notification
    function showToast(message) {
        toast.querySelector('.toast-message').textContent = message;
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('show'), 50);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.classList.add('hidden'), 300);
        }, 3000);
    }

    // Helper: Toggle button spinner
    function setSpinner(button, active) {
        const text = button.querySelector('.btn-text');
        const spinner = button.querySelector('.btn-spinner');
        if (active) {
            button.disabled = true;
            if (text) text.style.opacity = '0.7';
            if (spinner) spinner.classList.remove('hidden');
        } else {
            button.disabled = false;
            if (text) text.style.opacity = '1';
            if (spinner) spinner.classList.add('hidden');
        }
    }

    // Branch Guard: Enforce branch presence and main branch protection
    function validateBranchPreflight(branch) {
        const b = (branch || '').trim();
        if (!b) {
            showToast("⚠️ Working Branch is required (e.g. 'dbv2_merging').");
            if (branchInput) {
                branchInput.classList.add('input-error');
                branchInput.focus();
            }
            return false;
        }
        if (b.toLowerCase() === 'main') {
            const err = "Execution terminated: Operations on the 'main' branch are strictly prohibited to safeguard production code. Please specify a non-main development or feature branch (e.g. 'dbv2_merging').";
            showToast("🛑 Prohibited: Execution on 'main' branch is blocked!");
            alert(err);
            if (branchInput) {
                branchInput.classList.add('input-error');
                branchInput.focus();
            }
            return false;
        }
        if (branchInput) {
            branchInput.classList.remove('input-error');
        }
        return true;
    }

    // Helper: Get form credentials object
    function getCredentials() {
        return {
            username: usernameInput.value.trim ? usernameInput.value.trim() : usernameInput.value,
            api_token: tokenInput.value.trim(),
            account_id: accountInput.value.trim(),
            branch: branchInput ? branchInput.value.trim() : '',
            api_url: urlInput.value.trim()
        };
    }

    // Password Visibility Toggle (Show / Hide)
    const togglePasswordBtns = document.querySelectorAll('.toggle-password-btn');
    togglePasswordBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const targetId = btn.dataset.target;
            const input = document.getElementById(targetId);
            if (!input) return;

            const eyeIcon = btn.querySelector('.eye-icon');
            const eyeOffIcon = btn.querySelector('.eye-off-icon');

            if (input.type === 'password') {
                input.type = 'text';
                if (eyeIcon) eyeIcon.classList.add('hidden');
                if (eyeOffIcon) eyeOffIcon.classList.remove('hidden');
            } else {
                input.type = 'password';
                if (eyeIcon) eyeIcon.classList.remove('hidden');
                if (eyeOffIcon) eyeOffIcon.classList.add('hidden');
            }
        });
    });

    // Tabs Navigation handler
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.disabled) return;
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            const targetPane = document.getElementById(btn.dataset.tab);
            if (targetPane) targetPane.classList.add('active');
        });
    });

    // 1. Credentials Validation
    // Invalidate session when credentials are changed
    [usernameInput, tokenInput, accountInput, branchInput, urlInput].forEach(inp => {
        if (!inp) return;
        inp.addEventListener('input', () => {
            overallStatus.innerHTML = `<span class="status-dot disconnected"></span><span class="status-label">Disconnected</span>`;
            scanBtn.disabled = true;
            scanBtn.title = "Please enter credentials and click 'Validate Account' first";
            navTabs.migrate.disabled = true;
            navTabs.report.disabled = true;
        });
    });

    // 1. Credentials Validation
    validateBtn.addEventListener('click', async () => {
        const credentials = getCredentials();
        if (!credentials.username || !credentials.api_token || !credentials.account_id) {
            showToast("⚠️ Please enter your Boomi Username, API Token, and Account ID.");
            return;
        }
        if (!validateBranchPreflight(credentials.branch)) {
            return;
        }

        setSpinner(validateBtn, true);
        
        try {
            const response = await fetch('/api/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(credentials)
            });
            
            const data = await response.json();
            if (response.ok) {
                showToast(data.message || "Connection Successful");
                const activeBranch = data.branch_name || credentials.branch;
                overallStatus.innerHTML = `<span class="status-dot connected"></span><span class="status-label">Connected: <strong>${escapeHtml(activeBranch)}</strong></span>`;
                scanBtn.disabled = false;
                scanBtn.title = `Start discovery scan on branch '${activeBranch}'`;
                navTabs.scan.click();
            } else {
                throw new Error(data.detail || "Validation failed");
            }
        } catch (error) {
            showToast(error.message);
            overallStatus.innerHTML = `<span class="status-dot disconnected"></span><span class="status-label">Disconnected</span>`;
        } finally {
            setSpinner(validateBtn, false);
        }
    });

    // 2. Scan Discovery via SSE Stream
    const scanFolderInput = document.getElementById('scan-folder-filter');
    const scanProgressBox = document.getElementById('scan-progress-box');
    const scanElapsed = document.getElementById('scan-elapsed');
    const liveConnsStat = document.getElementById('live-conns-stat');
    const liveOpsStat = document.getElementById('live-ops-stat');
    const liveProfsStat = document.getElementById('live-profs-stat');
    const liveMapsStat = document.getElementById('live-maps-stat');
    const liveProcsStat = document.getElementById('live-procs-stat');

    scanBtn.addEventListener('click', async () => {
        const credentials = getCredentials();
        if (!credentials.username || !credentials.api_token || !credentials.account_id) {
            showToast("⚠️ Missing credentials. Please enter your Boomi Username, API Token, and Account ID, then validate first.");
            validateBtn.focus();
            return;
        }
        if (!validateBranchPreflight(credentials.branch)) {
            return;
        }

        setSpinner(scanBtn, true);
        scanResults.classList.add('hidden');
        if (scanProgressBox) scanProgressBox.classList.remove('hidden');
        
        if (liveConnsStat) liveConnsStat.textContent = '0 found';
        if (liveOpsStat) liveOpsStat.textContent = '0 found';
        if (liveProfsStat) liveProfsStat.textContent = '0 found';
        if (liveMapsStat) liveMapsStat.textContent = 'Searching maps & caches...';
        if (liveProcsStat) liveProcsStat.textContent = 'Searching DB processes...';
        
        let startTime = Date.now();
        const timerInterval = setInterval(() => {
            if (scanElapsed) {
                const elapsedSec = Math.floor((Date.now() - startTime) / 1000);
                scanElapsed.textContent = `${elapsedSec}s elapsed`;
            }
        }, 1000);

        const payload = {
            ...credentials,
            folder_filter: scanFolderInput ? scanFolderInput.value.trim() : "",
            session_id: tabSessionId
        };
        
        try {
            const response = await fetch('/api/scan-stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || `Scan failed (HTTP ${response.status})`);
            }
            if (!response.body) {
                throw new Error("Streaming not supported or failed to connect");
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let finalResults = null;
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // Keep partial line
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.slice(6).trim();
                        if (!jsonStr) continue;
                        
                        try {
                            const eventData = JSON.parse(jsonStr);
                            if (eventData.type === 'progress') {
                                if (eventData.category === 'connections' && liveConnsStat) {
                                    liveConnsStat.textContent = `${eventData.count} found (page ${eventData.page})`;
                                } else if (eventData.category === 'operations' && liveOpsStat) {
                                    liveOpsStat.textContent = `${eventData.count} found (page ${eventData.page})`;
                                } else if (eventData.category === 'profiles' && liveProfsStat) {
                                    liveProfsStat.textContent = `${eventData.count} found (page ${eventData.page})`;
                                } else if (eventData.category === 'maps_caches' && liveMapsStat) {
                                    liveMapsStat.textContent = `${eventData.count}`;
                                } else if (eventData.category === 'processes' && liveProcsStat) {
                                    liveProcsStat.textContent = String(eventData.count).includes('DB') ? `${eventData.count}` : `${eventData.count} referencing DB`;
                                }
                            } else if (eventData.type === 'complete') {
                                finalResults = eventData.results;
                            } else if (eventData.type === 'error') {
                                throw new Error(eventData.error);
                            }
                        } catch (err) {
                            if (err.message && err.message.includes('Validation')) throw err;
                            console.error("Error parsing scan SSE:", err);
                        }
                    }
                }
            }
            
            if (finalResults) {
                if (finalResults.folder_not_found) {
                    showToast(`⚠️ Folder "${finalResults.searched_folder}" not found in Boomi account.`);
                } else {
                    showToast("Discovery scan completed successfully!");
                }
                renderScanResults(finalResults);
                renderMigrationProcessTree(finalResults, '');
                updateMigrationSelectionUI();
                navTabs.migrate.disabled = false;
                downloadReportBtn.classList.remove('hidden');
                
                // Prefill folder filter in migration tab if user used it
                if (folderFilter && scanFolderInput && scanFolderInput.value) {
                    folderFilter.value = scanFolderInput.value;
                    updateMigrationSelectionUI();
                }
            } else {
                throw new Error("Scan finished without returning results.");
            }
        } catch (error) {
            showToast(error.message);
        } finally {
            clearInterval(timerInterval);
            if (scanProgressBox) scanProgressBox.classList.add('hidden');
            setSpinner(scanBtn, false);
        }
    });

    let currentScanData = null;
    let activeCategory = 'folders';
    let displayedCount = 50;

    const catButtons = document.querySelectorAll('.cat-btn');
    const compSearch = document.getElementById('component-search');
    const loadMoreBtn = document.getElementById('load-more-btn');
    const loadMoreContainer = document.getElementById('load-more-container');

    catButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            catButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeCategory = btn.dataset.cat;
            displayedCount = 50;
            renderComponentList();
        });
    });

    if (compSearch) {
        compSearch.addEventListener('input', () => {
            displayedCount = 50;
            renderComponentList();
        });
    }

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', () => {
            displayedCount += 50;
            renderComponentList();
        });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    const downloadExcelBtn = document.getElementById('download-excel-btn');
    if (downloadExcelBtn) {
        downloadExcelBtn.addEventListener('click', () => {
            const creds = getCredentials();
            const accId = encodeURIComponent(creds.account_id || '');
            const url = `/api/download-report-excel?session_id=${tabSessionId}&account_id=${accId}`;
            showToast(`Generating and downloading Excel report for ${creds.account_id || 'account'}...`);
            const link = document.createElement('a');
            link.href = url;
            link.download = `legacy_db_audit_report_${creds.account_id || 'account'}.xlsx`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }

    // Download Scan Report (Markdown)
    if (downloadReportBtn) {
        downloadReportBtn.addEventListener('click', () => {
            const creds = getCredentials();
            const accId = encodeURIComponent(creds.account_id || '');
            const url = `/api/download-report?session_id=${tabSessionId}&account_id=${accId}`;
            showToast(`Downloading Markdown report for ${creds.account_id || 'account'}...`);
            const link = document.createElement('a');
            link.href = url;
            link.download = `legacy_db_audit_report_${creds.account_id || 'account'}.md`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }

    const usageCache = {};

    async function toggleProcessUsage(container, compId, version) {
        if (!container) return;
        
        if (!container.classList.contains('hidden')) {
            container.classList.add('hidden');
            return;
        }

        container.classList.remove('hidden');
        if (usageCache[compId]) {
            renderUsageContent(container, usageCache[compId]);
            return;
        }

        container.innerHTML = `<div style="font-size: 0.8rem; color: #80deea; padding: 6px 0;"><span class="btn-spinner" style="display:inline-block; vertical-align:middle; width:12px; height:12px; margin-right:6px;"></span> Resolving referenced processes from Boomi API...</div>`;

        try {
            const res = await fetch('/api/component-usage', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    credentials: getCredentials(),
                    component_id: compId,
                    version: version || 1
                })
            });
            const data = await res.json();
            if (res.ok) {
                usageCache[compId] = data.used_in || [];
                renderUsageContent(container, usageCache[compId]);
            } else {
                throw new Error(data.detail || "Failed to fetch usage");
            }
        } catch (e) {
            container.innerHTML = `<div style="font-size: 0.8rem; color: #ef5350;">Error resolving dependencies: ${escapeHtml(e.message)}</div>`;
        }
    }

    function getBoomiComponentUrl(componentId) {
        if (!componentId) return '#';
        const creds = getCredentials();
        const accountId = creds.account_id || '';
        if (accountId) {
            return `https://platform.boomi.com/AtomSphere.html#build;accountId=${encodeURIComponent(accountId)};components=${encodeURIComponent(componentId)}`;
        }
        return `https://platform.boomi.com/AtomSphere.html#build;components=${encodeURIComponent(componentId)}`;
    }

    function renderUsageContent(container, processes) {
        if (!processes || processes.length === 0) {
            container.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-secondary); padding: 4px 0;">⚡ <em>Not referenced in any process (Orphan component).</em></div>`;
            return;
        }

        let html = `<div style="margin-top: 6px; padding: 8px 12px; background: rgba(0,0,0,0.3); border-radius: 8px; border-left: 3px solid #00bcd4;">
            <div style="font-size: 0.75rem; font-weight: 600; color: #80deea; margin-bottom: 4px;">USED IN ${processes.length} PROCESS(ES) / COMPONENT(S):</div>`;
        
        processes.forEach(p => {
            const boomiUrl = getBoomiComponentUrl(p.id);
            html += `<div style="font-size: 0.8rem; margin: 3px 0; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <span>📌 <a href="${boomiUrl}" target="_blank" rel="noopener noreferrer" class="component-link" title="Open '${escapeHtml(p.name)}' directly in Boomi Build tab" style="font-weight: 700; color: #80deea;" onclick="event.stopPropagation();">${escapeHtml(p.name)} <svg style="width:11px; height:11px; vertical-align:middle; fill:currentColor;" viewBox="0 0 24 24"><path d="M14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3m-2 16H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7z"/></svg></a> <span style="color: var(--text-secondary); font-size: 0.75rem;">(${escapeHtml(p.type)}) in 📁 ${escapeHtml(p.folder)}</span></span>
                <code style="font-size: 0.7rem; background: rgba(255,255,255,0.08); padding: 1px 4px; border-radius: 3px;">${p.id}</code>
            </div>`;
        });
        html += `</div>`;
        container.innerHTML = html;
    }

    function buildHierarchicalTree(data, query) {
        const root = {
            name: 'Root',
            fullPath: '',
            depth: 0,
            children: {},
            direct: {
                connections: [],
                operations: [],
                profiles: [],
                maps: [],
                caches: [],
                processes: []
            },
            directCount: 0,
            rollupCount: 0,
            rollup: {
                connections: 0,
                operations: 0,
                profiles: 0,
                maps: 0,
                caches: 0,
                processes: 0
            }
        };

        // Determine root folder dynamically from scan data or existing component paths
        let defaultRoot = (data && data.root_folder_name) || 
                          (typeof currentScanData !== 'undefined' && currentScanData && currentScanData.root_folder_name) || '';
        if (!defaultRoot) {
            const allItems = [
                ...(data.connections || []),
                ...(data.operations || []),
                ...(data.profiles || []),
                ...(data.maps || []),
                ...(data.caches || []),
                ...(data.processes || [])
            ];
            for (const item of allItems) {
                const fp = (item.folderPath || '').trim().replace(/\\+/g, '/').replace(/\/+/g, '/');
                if (fp && fp !== 'Root' && fp.includes('/')) {
                    defaultRoot = fp.split('/')[0].trim();
                    if (defaultRoot) break;
                }
            }
        }
        if (!defaultRoot) defaultRoot = 'Root';

        const addItems = (items, category) => {
            (items || []).forEach(item => {
                let rawPath = (item.folderPath || item.folderName || '').trim();
                // Normalize slashes
                rawPath = rawPath.replace(/\\+/g, '/').replace(/\/+/g, '/');
                if (rawPath.startsWith('/')) rawPath = rawPath.slice(1);
                if (rawPath.endsWith('/')) rawPath = rawPath.slice(0, -1);
                
                if (!rawPath || rawPath === 'Root') {
                    rawPath = defaultRoot;
                } else if (defaultRoot !== 'Root' && rawPath !== defaultRoot && !rawPath.startsWith(defaultRoot + '/')) {
                    rawPath = defaultRoot + '/' + rawPath;
                }

                const segments = rawPath.split('/');
                let currentNode = root;
                let currentFullPath = '';

                segments.forEach((seg, idx) => {
                    seg = seg.trim() || 'Folder';
                    currentFullPath = currentFullPath ? `${currentFullPath}/${seg}` : seg;
                    
                    if (!currentNode.children[seg]) {
                        currentNode.children[seg] = {
                            name: seg,
                            fullPath: currentFullPath,
                            depth: idx + 1,
                            children: {},
                            direct: {
                                connections: [],
                                operations: [],
                                profiles: [],
                                maps: [],
                                caches: [],
                                processes: []
                            },
                            directCount: 0,
                            rollupCount: 0,
                            rollup: {
                                connections: 0,
                                operations: 0,
                                profiles: 0,
                                maps: 0,
                                caches: 0,
                                processes: 0
                            }
                        };
                    }
                    currentNode = currentNode.children[seg];
                });

                currentNode.direct[category].push(item);
            });
        };

        addItems(data.connections, 'connections');
        addItems(data.operations, 'operations');
        addItems(data.profiles, 'profiles');
        addItems(data.maps, 'maps');
        addItems(data.caches, 'caches');
        addItems(data.processes, 'processes');

        // Post-order traversal to compute rollup counts
        function computeRollups(node) {
            node.directCount = node.direct.connections.length +
                               node.direct.operations.length +
                               node.direct.profiles.length +
                               node.direct.maps.length +
                               node.direct.caches.length +
                               node.direct.processes.length;

            node.rollup = {
                connections: node.direct.connections.length,
                operations: node.direct.operations.length,
                profiles: node.direct.profiles.length,
                maps: node.direct.maps.length,
                caches: node.direct.caches.length,
                processes: node.direct.processes.length
            };

            Object.values(node.children).forEach(child => {
                computeRollups(child);
                node.rollup.connections += child.rollup.connections;
                node.rollup.operations += child.rollup.operations;
                node.rollup.profiles += child.rollup.profiles;
                node.rollup.maps += child.rollup.maps;
                node.rollup.caches += child.rollup.caches;
                node.rollup.processes += child.rollup.processes;
            });

            node.rollupCount = node.rollup.connections +
                               node.rollup.operations +
                               node.rollup.profiles +
                               node.rollup.maps +
                               node.rollup.caches +
                               node.rollup.processes;
        }

        computeRollups(root);

        const q = (query || '').toLowerCase().trim();

        // Recursive filter by search query
        function filterNode(node) {
            const folderMatches = node.name.toLowerCase().includes(q) || node.fullPath.toLowerCase().includes(q);

            const matchItem = item => (item.name && item.name.toLowerCase().includes(q)) ||
                                     ((item.componentId || item.id) && (item.componentId || item.id).toLowerCase().includes(q));

            const filteredDirect = {
                connections: folderMatches ? [...node.direct.connections] : node.direct.connections.filter(matchItem),
                operations: folderMatches ? [...node.direct.operations] : node.direct.operations.filter(matchItem),
                profiles: folderMatches ? [...node.direct.profiles] : node.direct.profiles.filter(matchItem),
                maps: folderMatches ? [...node.direct.maps] : node.direct.maps.filter(matchItem),
                caches: folderMatches ? [...node.direct.caches] : node.direct.caches.filter(matchItem),
                processes: folderMatches ? [...node.direct.processes] : node.direct.processes.filter(matchItem)
            };

            const directFilteredCount = filteredDirect.connections.length +
                                        filteredDirect.operations.length +
                                        filteredDirect.profiles.length +
                                        filteredDirect.maps.length +
                                        filteredDirect.caches.length +
                                        filteredDirect.processes.length;

            const filteredChildren = {};
            let childrenRollupCount = 0;
            const childRollupBreakdown = {
                connections: 0, operations: 0, profiles: 0, maps: 0, caches: 0, processes: 0
            };

            Object.entries(node.children).forEach(([childName, childNode]) => {
                const filteredChild = filterNode(childNode);
                if (filteredChild) {
                    filteredChildren[childName] = filteredChild;
                    childrenRollupCount += filteredChild.rollupCount;
                    childRollupBreakdown.connections += filteredChild.rollup.connections;
                    childRollupBreakdown.operations += filteredChild.rollup.operations;
                    childRollupBreakdown.profiles += filteredChild.rollup.profiles;
                    childRollupBreakdown.maps += filteredChild.rollup.maps;
                    childRollupBreakdown.caches += filteredChild.rollup.caches;
                    childRollupBreakdown.processes += filteredChild.rollup.processes;
                }
            });

            const totalFilteredCount = directFilteredCount + childrenRollupCount;
            if (totalFilteredCount === 0 && !folderMatches) {
                return null;
            }

            return {
                name: node.name,
                fullPath: node.fullPath,
                depth: node.depth,
                children: filteredChildren,
                direct: filteredDirect,
                directCount: directFilteredCount,
                rollupCount: totalFilteredCount,
                rollup: {
                    connections: filteredDirect.connections.length + childRollupBreakdown.connections,
                    operations: filteredDirect.operations.length + childRollupBreakdown.operations,
                    profiles: filteredDirect.profiles.length + childRollupBreakdown.profiles,
                    maps: filteredDirect.maps.length + childRollupBreakdown.maps,
                    caches: filteredDirect.caches.length + childRollupBreakdown.caches,
                    processes: filteredDirect.processes.length + childRollupBreakdown.processes
                }
            };
        }

        function getEffectiveMainFolders(rootNode) {
            const target = (data && data.target_folder) ? data.target_folder.trim().toLowerCase() : 
                           (scanFolderInput && scanFolderInput.value ? scanFolderInput.value.trim().toLowerCase() : '');
            if (target) {
                let foundNode = null;
                function searchTarget(node) {
                    if (node.name && (node.name.toLowerCase() === target || node.fullPath.toLowerCase().endsWith('/' + target) || node.fullPath.toLowerCase() === target)) {
                        foundNode = node;
                        return;
                    }
                    for (const child of Object.values(node.children || {})) {
                        searchTarget(child);
                        if (foundNode) return;
                    }
                }
                searchTarget(rootNode);
                if (foundNode) {
                    function resetDepth(n, d) {
                        n.depth = d;
                        Object.values(n.children || {}).forEach(c => resetDepth(c, d + 1));
                    }
                    resetDepth(foundNode, 0);
                    return [foundNode];
                }
            }
            return Object.values(rootNode.children || {});
        }

        if (q) {
            const filteredRoot = filterNode(root);
            return filteredRoot ? getEffectiveMainFolders(filteredRoot) : [];
        }

        return getEffectiveMainFolders(root);
    }

    // Render Fast Component Explorer
    function renderScanResults(data) {
        currentScanData = data;
        scanResults.classList.remove('hidden');
        
        const connsCount = (data.connections || []).length;
        const opsCount = (data.operations || []).length;
        const profsCount = (data.profiles || []).length;
        const mapsCount = (data.maps || []).length;
        const cachesCount = (data.caches || []).length;
        const procsCount = (data.processes || []).length;
        
        const statConns = document.getElementById('stat-conns');
        const statOps = document.getElementById('stat-ops');
        const statProfs = document.getElementById('stat-profiles');
        const statMaps = document.getElementById('stat-maps');
        const statCaches = document.getElementById('stat-caches');
        const statProcs = document.getElementById('stat-processes');
        
        if (statConns) statConns.textContent = connsCount;
        if (statOps) statOps.textContent = opsCount;
        if (statProfs) statProfs.textContent = profsCount;
        if (statMaps) statMaps.textContent = mapsCount;
        if (statCaches) statCaches.textContent = cachesCount;
        if (statProcs) statProcs.textContent = procsCount;
        
        // Calculate Main Folders and Nested Subfolders accurately
        const rootFolders = buildHierarchicalTree(data, '');
        const mainFoldersCount = rootFolders.length;
        let totalSubfoldersCount = 0;
        const countSubs = node => {
            const subs = Object.values(node.children || {});
            totalSubfoldersCount += subs.length;
            subs.forEach(countSubs);
        };
        rootFolders.forEach(countSubs);

        const catFolders = document.getElementById('cat-folders-count');
        const catConns = document.getElementById('cat-conns-count');
        const catOps = document.getElementById('cat-ops-count');
        const catProfs = document.getElementById('cat-profs-count');
        const catMaps = document.getElementById('cat-maps-count');
        const catCaches = document.getElementById('cat-caches-count');
        const catProcs = document.getElementById('cat-procs-count');
        
        if (catFolders) {
            catFolders.textContent = totalSubfoldersCount > 0 
                ? `${mainFoldersCount} Main (${totalSubfoldersCount} Subfolders)` 
                : `${mainFoldersCount} Main Folder`;
            const card = catFolders.closest('.category-card') || catFolders.parentElement;
            if (card) {
                card.title = `${mainFoldersCount} Main Folder(s), ${totalSubfoldersCount} Nested Subfolder(s)`;
            }
        }
        if (catConns) catConns.textContent = connsCount;
        if (catOps) catOps.textContent = opsCount;
        if (catProfs) catProfs.textContent = profsCount;
        if (catMaps) catMaps.textContent = mapsCount;
        if (catCaches) catCaches.textContent = cachesCount;
        if (catProcs) catProcs.textContent = procsCount;
        
        if (downloadExcelBtn) downloadExcelBtn.classList.remove('hidden');
        if (downloadReportBtn) downloadReportBtn.classList.remove('hidden');
        
        displayedCount = 50;
        renderComponentList();
    }

    function renderComponentList() {
        if (!currentScanData) return;
        
        dependencyTree.innerHTML = '';
        const query = (compSearch ? compSearch.value : '').toLowerCase().trim();

        if (activeCategory === 'folders') {
            renderFolderView(query);
        } else {
            renderFlatCategoryView(activeCategory, query);
        }
    }

    function renderFolderView(query) {
        const rootFolders = buildHierarchicalTree(currentScanData, query);
        rootFolders.sort((a, b) => a.name.localeCompare(b.name));
        
        const slice = rootFolders.slice(0, displayedCount);

        if (slice.length === 0) {
            dependencyTree.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-secondary); background: #fff; border-radius: 12px; border: 1px dashed var(--border-color);">
                <div style="font-size: 1.2rem; margin-bottom: 6px;">📂 No folders or components found</div>
                <div style="font-size: 0.85rem;">No matching items for query "${escapeHtml(query)}"</div>
            </div>`;
            if (loadMoreContainer) loadMoreContainer.classList.add('hidden');
            return;
        }

        const fragment = document.createDocumentFragment();

        slice.forEach(folderNode => {
            const el = createFolderTreeNodeElement(folderNode, query, 0);
            fragment.appendChild(el);
        });

        dependencyTree.appendChild(fragment);

        if (loadMoreContainer) {
            if (rootFolders.length > displayedCount) {
                loadMoreContainer.classList.remove('hidden');
                loadMoreBtn.textContent = `Show More Root Folders (${rootFolders.length - displayedCount} remaining)`;
            } else {
                loadMoreContainer.classList.add('hidden');
            }
        }
    }

    function createFolderTreeNodeElement(folder, query, depth = 0) {
        const childFolders = Object.values(folder.children || {});
        childFolders.sort((a, b) => a.name.localeCompare(b.name));
        const hasSubfolders = childFolders.length > 0;
        const hasDirectItems = folder.directCount > 0;
        const isMainFolder = depth === 0;

        const folderEl = document.createElement('div');
        folderEl.className = isMainFolder ? 'main-folder-node' : 'subfolder-node';
        folderEl.style.marginBottom = isMainFolder ? '16px' : '6px';
        folderEl.style.background = '#ffffff';
        folderEl.style.borderRadius = isMainFolder ? '12px' : '8px';
        folderEl.style.border = isMainFolder ? '1px solid #cbd5e1' : '1px solid #e2e8f0';
        folderEl.style.overflow = 'hidden';
        folderEl.style.boxShadow = isMainFolder ? '0 2px 8px rgba(0,0,0,0.04)' : 'none';

        // Header
        const header = document.createElement('div');
        header.className = isMainFolder ? 'main-folder-header' : 'subfolder-header';
        header.style.cursor = 'pointer';
        header.style.padding = isMainFolder ? '13px 18px' : '8px 12px';
        header.style.display = 'flex';
        header.style.justifyContent = 'space-between';
        header.style.alignItems = 'center';
        header.style.userSelect = 'none';
        header.style.background = isMainFolder ? '#ffffff' : '#f8fafc';
        header.style.transition = 'background 0.15s ease';

        header.addEventListener('mouseenter', () => {
            header.style.background = isMainFolder ? '#f8fafc' : '#f1f5f9';
        });
        header.addEventListener('mouseleave', () => {
            header.style.background = isMainFolder ? '#ffffff' : '#f8fafc';
        });

        const rollup = folder.rollup;
        const subfolderCountText = hasSubfolders ? `${childFolders.length} subfolder${childFolders.length > 1 ? 's' : ''}` : '';
        const countBreakdown = isMainFolder
            ? `${folder.rollupCount} total items across ${childFolders.length} subfolders`
            : (hasSubfolders 
                ? `${folder.rollupCount} items (${folder.directCount} direct, ${folder.rollupCount - folder.directCount} in ${subfolderCountText})`
                : `${folder.directCount} item${folder.directCount !== 1 ? 's' : ''}`);

        header.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; max-width: 65%;">
                <span class="folder-chevron" style="display: inline-block; transition: transform 0.2s ease; font-size: 0.75rem; color: #6c5ce7;">▶</span>
                <span style="font-size: ${isMainFolder ? '1.05rem' : '0.88rem'}; font-weight: 700; color: #1e293b;">${isMainFolder ? '📁' : '📂'} ${escapeHtml(folder.name)}</span>
                <span style="font-size: 0.65rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.4px; background: ${isMainFolder ? '#e0e7ff' : '#e2e8f0'}; color: ${isMainFolder ? '#4338ca' : '#475569'};">
                    ${isMainFolder ? 'Main Folder' : (depth === 1 ? 'Subfolder' : 'Sub-subfolder')}
                </span>
                <span style="font-size: 0.72rem; color: #64748b; font-family: monospace;">(${escapeHtml(folder.fullPath)})</span>
                <span style="font-size: 0.75rem; color: #475569; background: #ffffff; border: 1px solid #e2e8f0; padding: 2px 8px; border-radius: 6px; font-weight: 600;">
                    ${countBreakdown}
                </span>
            </div>
            <div style="display: flex; gap: 6px; font-size: 0.72rem; flex-wrap: wrap; justify-content: flex-end;">
                ${rollup.processes > 0 ? `<span class="badge process" title="${rollup.processes} DB Processes">${rollup.processes} Procs</span>` : ''}
                ${rollup.maps > 0 ? `<span class="badge map" title="${rollup.maps} Maps using DB Profiles">${rollup.maps} Maps</span>` : ''}
                ${rollup.caches > 0 ? `<span class="badge cache" title="${rollup.caches} DB Document Caches">${rollup.caches} Caches</span>` : ''}
                ${rollup.connections > 0 ? `<span class="badge connection" title="${rollup.connections} DB Connections">${rollup.connections} Conns</span>` : ''}
                ${rollup.operations > 0 ? `<span class="badge operation" title="${rollup.operations} DB Operations">${rollup.operations} Ops</span>` : ''}
                ${rollup.profiles > 0 ? `<span class="badge profile" title="${rollup.profiles} DB Profiles">${rollup.profiles} Profs</span>` : ''}
            </div>
        `;

        // Content
        const content = document.createElement('div');
        content.className = isMainFolder ? 'main-folder-content' : 'subfolder-content';
        content.style.display = 'none';
        content.style.padding = isMainFolder ? '12px 16px 14px 18px' : '8px 12px 10px 14px';
        content.style.background = isMainFolder ? '#fcfdfe' : '#ffffff';
        content.style.borderTop = '1px solid #e2e8f0';

        const chevron = header.querySelector('.folder-chevron');

        let isRendered = false;
        const renderContents = () => {
            if (isRendered) return;
            isRendered = true;

            // 1. Render nested subfolders if any
            if (hasSubfolders) {
                const subfolderContainer = document.createElement('div');
                subfolderContainer.className = 'folder-subfolders-container';
                subfolderContainer.style.borderLeft = '2px dashed #cbd5e1';
                subfolderContainer.style.paddingLeft = '14px';
                subfolderContainer.style.marginLeft = isMainFolder ? '8px' : '10px';
                subfolderContainer.style.marginTop = '4px';
                subfolderContainer.style.marginBottom = hasDirectItems ? '16px' : '6px';
                
                const subfolderHeader = document.createElement('div');
                subfolderHeader.style.fontSize = '0.73rem';
                subfolderHeader.style.fontWeight = '700';
                subfolderHeader.style.color = '#4f46e5';
                subfolderHeader.style.marginBottom = '8px';
                subfolderHeader.style.textTransform = 'uppercase';
                subfolderHeader.style.letterSpacing = '0.5px';
                subfolderHeader.textContent = `📂 Subfolders of "${folder.name}" (${childFolders.length}):`;
                subfolderContainer.appendChild(subfolderHeader);

                childFolders.forEach(subChild => {
                    const subEl = createFolderTreeNodeElement(subChild, query, depth + 1);
                    subfolderContainer.appendChild(subEl);
                });

                content.appendChild(subfolderContainer);
            }

            // 2. Render direct items in this folder level
            if (hasDirectItems) {
                const directContainer = document.createElement('div');
                directContainer.className = 'folder-direct-items-container';

                if (hasSubfolders) {
                    const directHeader = document.createElement('div');
                    directHeader.style.fontSize = '0.73rem';
                    directHeader.style.fontWeight = '700';
                    directHeader.style.color = '#334155';
                    directHeader.style.margin = '14px 0 8px 0';
                    directHeader.style.textTransform = 'uppercase';
                    directHeader.style.letterSpacing = '0.5px';
                    directHeader.textContent = `📄 Direct Components in "${folder.name}" (${folder.directCount}):`;
                    directContainer.appendChild(directHeader);
                }

                renderDirectFolderItems(directContainer, folder.direct);
                content.appendChild(directContainer);
            }
        };

        header.addEventListener('click', () => {
            const isExpanded = content.style.display !== 'none';
            if (isExpanded) {
                content.style.display = 'none';
                chevron.style.transform = 'rotate(0deg)';
            } else {
                content.style.display = 'block';
                chevron.style.transform = 'rotate(90deg)';
                renderContents();
            }
        });

        // Auto-expand Main Folder (depth 0) or on search query
        if (depth === 0 || query) {
            content.style.display = 'block';
            chevron.style.transform = 'rotate(90deg)';
            renderContents();
        }

        folderEl.appendChild(header);
        folderEl.appendChild(content);
        return folderEl;
    }

    function renderDirectFolderItems(container, direct) {
        let html = '';

        const createItemHtml = (item, type, badgeClass, badgeLabel, showUsage) => {
            const compId = item.componentId || item.id || '';
            const boomiUrl = getBoomiComponentUrl(compId);
            return `
            <div class="tree-node" style="margin-bottom: 8px; padding: 9px 13px; background: #ffffff; border-radius: 8px; border: 1px solid rgba(0,0,0,0.06); box-shadow: 0 1px 3px rgba(0,0,0,0.02);">
                <div class="tree-node-label" style="display: flex; justify-content: space-between; align-items: center; width: 100%; flex-wrap: wrap; gap: 6px;">
                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <span class="badge ${badgeClass}">${badgeLabel}</span>
                        <a href="${boomiUrl}" target="_blank" rel="noopener noreferrer" class="component-link" title="Open '${escapeHtml(item.name)}' directly in Boomi Build tab" onclick="event.stopPropagation();" style="font-size: 0.88rem; font-weight: 600;">
                            ${escapeHtml(item.name)}
                            <svg style="width:11px; height:11px; vertical-align:middle; fill:currentColor;" viewBox="0 0 24 24"><path d="M14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3m-2 16H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7z"/></svg>
                        </a>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <code style="font-size: 0.75rem; background: #f0edff; color: #6c5ce7; padding: 2px 7px; border-radius: 4px; font-weight: 600;">${compId}</code>
                        ${showUsage ? `<button type="button" class="btn btn-outline inner-usage-btn" data-id="${compId}" data-ver="${item.version || 1}" style="padding: 3px 10px; font-size: 0.72rem; border-color: rgba(108,92,231,0.3); color: #6c5ce7; background: #ffffff;">🔍 Used In</button>` : ''}
                    </div>
                </div>
                <div class="inner-usage-container hidden" style="margin-top: 6px;"></div>
            </div>
            `;
        };

        if (direct.processes && direct.processes.length > 0) {
            html += `<div style="font-size: 0.75rem; font-weight: 700; color: #2e7d32; margin: 6px 0 4px 0; text-transform: uppercase; letter-spacing: 0.3px;">🚀 Direct DB Processes (${direct.processes.length}):</div>`;
            direct.processes.forEach(p => {
                html += createItemHtml(p, 'process', 'process', 'Process', false);
            });
        }

        if (direct.maps && direct.maps.length > 0) {
            html += `<div style="font-size: 0.75rem; font-weight: 700; color: #d84315; margin: 10px 0 4px 0; text-transform: uppercase; letter-spacing: 0.3px;">🗺️ Direct Maps using DB Profiles (${direct.maps.length}):</div>`;
            direct.maps.forEach(m => {
                html += createItemHtml(m, 'map', 'map', 'Map', true);
            });
        }

        if (direct.caches && direct.caches.length > 0) {
            html += `<div style="font-size: 0.75rem; font-weight: 700; color: #283593; margin: 10px 0 4px 0; text-transform: uppercase; letter-spacing: 0.3px;">💾 Direct Document Caches (${direct.caches.length}):</div>`;
            direct.caches.forEach(c => {
                html += createItemHtml(c, 'cache', 'cache', 'Cache', true);
            });
        }

        if (direct.connections && direct.connections.length > 0) {
            html += `<div style="font-size: 0.75rem; font-weight: 700; color: #e65100; margin: 10px 0 4px 0; text-transform: uppercase; letter-spacing: 0.3px;">🔌 Direct DB Connections (${direct.connections.length}):</div>`;
            direct.connections.forEach(c => {
                html += createItemHtml(c, 'connection', 'connection', 'Connection', true);
            });
        }

        if (direct.operations && direct.operations.length > 0) {
            html += `<div style="font-size: 0.75rem; font-weight: 700; color: #7b1fa2; margin: 10px 0 4px 0; text-transform: uppercase; letter-spacing: 0.3px;">⚙️ Direct DB Operations (${direct.operations.length}):</div>`;
            direct.operations.forEach(o => {
                html += createItemHtml(o, 'operation', 'operation', 'Operation', true);
            });
        }

        if (direct.profiles && direct.profiles.length > 0) {
            html += `<div style="font-size: 0.75rem; font-weight: 700; color: #00838f; margin: 10px 0 4px 0; text-transform: uppercase; letter-spacing: 0.3px;">📄 Direct DB Profiles (${direct.profiles.length}):</div>`;
            direct.profiles.forEach(p => {
                html += createItemHtml(p, 'profile', 'profile', 'Profile', true);
            });
        }

        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;

        // Attach event listeners for on-demand where-used buttons inside the folder
        tempDiv.querySelectorAll('.inner-usage-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const parentNode = btn.closest('.tree-node');
                const usageContainer = parentNode.querySelector('.inner-usage-container');
                toggleProcessUsage(usageContainer, btn.dataset.id, btn.dataset.ver);
            });
        });

        container.appendChild(tempDiv);
    }

    function renderFlatCategoryView(category, query) {
        const list = currentScanData[category] || [];
        
        const filtered = list.filter(item => {
            if (!query) return true;
            return (item.name && item.name.toLowerCase().includes(query)) ||
                   ((item.componentId || item.id) && (item.componentId || item.id).toLowerCase().includes(query)) ||
                   ((item.folderPath || item.folderName) && (item.folderPath || item.folderName).toLowerCase().includes(query));
        });
        
        const slice = filtered.slice(0, displayedCount);
        
        if (slice.length === 0) {
            dependencyTree.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--text-secondary);">No ${category} found matching "${escapeHtml(query)}".</div>`;
            if (loadMoreContainer) loadMoreContainer.classList.add('hidden');
            return;
        }
        
        let badgeClass = 'connection';
        let badgeLabel = 'Connection';
        let showUsage = true;

        if (category === 'connections') { badgeClass = 'connection'; badgeLabel = 'Connection'; }
        else if (category === 'operations') { badgeClass = 'operation'; badgeLabel = 'Operation'; }
        else if (category === 'profiles') { badgeClass = 'profile'; badgeLabel = 'Profile'; }
        else if (category === 'maps') { badgeClass = 'map'; badgeLabel = 'Map (DB)'; }
        else if (category === 'caches') { badgeClass = 'cache'; badgeLabel = 'Cache (DB)'; }
        else if (category === 'processes') { badgeClass = 'process'; badgeLabel = 'Process'; showUsage = false; }
        
        const fragment = document.createDocumentFragment();
        slice.forEach(item => {
            const compId = item.componentId || item.id || '';
            const boomiUrl = getBoomiComponentUrl(compId);
            const node = document.createElement('div');
            node.className = 'tree-node';
            node.style.marginBottom = '9px';
            node.style.padding = '11px 15px';
            node.style.background = '#ffffff';
            node.style.borderRadius = '10px';
            node.style.border = '1px solid rgba(0,0,0,0.07)';
            node.style.boxShadow = '0 1px 4px rgba(0,0,0,0.02)';
            
            node.innerHTML = `
                <div class="tree-node-label" style="display: flex; justify-content: space-between; align-items: center; width: 100%; flex-wrap: wrap; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <span class="badge ${badgeClass}">${badgeLabel}</span>
                        <a href="${boomiUrl}" target="_blank" rel="noopener noreferrer" class="component-link" title="Open '${escapeHtml(item.name)}' directly in Boomi Build tab" style="font-size: 0.95rem; font-weight: 700;">
                            ${escapeHtml(item.name)}
                            <svg style="width:12px; height:12px; vertical-align:middle; fill:currentColor;" viewBox="0 0 24 24"><path d="M14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3m-2 16H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7z"/></svg>
                        </a>
                        <span style="font-size: 0.8rem; color: #636e72; background: #f0f2f8; padding: 2px 8px; border-radius: 6px;">📁 ${escapeHtml(item.folderPath || item.folderName || 'Root')}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <code style="font-size: 0.75rem; background: #f0edff; color: #6c5ce7; padding: 3px 8px; border-radius: 4px; font-weight: 600;">${compId} (v${item.version || 1})</code>
                        ${showUsage ? `<button type="button" class="btn btn-outline usage-btn" style="padding: 3px 10px; font-size: 0.75rem; border-color: rgba(108,92,231,0.3); color: #6c5ce7; background: #ffffff;">🔍 Used In Processes</button>` : ''}
                    </div>
                </div>
                <div class="usage-details-container hidden" style="margin-top: 8px;"></div>
            `;
            
            if (showUsage) {
                const usageBtn = node.querySelector('.usage-btn');
                const usageContainer = node.querySelector('.usage-details-container');
                usageBtn.addEventListener('click', () => {
                    toggleProcessUsage(usageContainer, compId, item.version || 1);
                });
            }

            fragment.appendChild(node);
        });
        dependencyTree.appendChild(fragment);
        
        if (loadMoreContainer) {
            if (filtered.length > displayedCount) {
                loadMoreContainer.classList.remove('hidden');
                loadMoreBtn.textContent = `Show More (${filtered.length - displayedCount} remaining)`;
            } else {
                loadMoreContainer.classList.add('hidden');
            }
        }
    }

    // ==========================================
    // Tab 2: Migration Agent - Process Hierarchy & Search
    // ==========================================
    function highlightMatch(text, query) {
        if (!text) return '';
        if (!query) return escapeHtml(text);
        const escaped = escapeHtml(text);
        const qEscaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${qEscaped})`, 'gi');
        return escaped.replace(regex, '<span class="highlight-match">$1</span>');
    }

    function updateMigrationSelectionUI() {
        const cCount = selectedConnectionIds.size;
        const oCount = selectedOperationIds.size;
        const profCount = selectedProfileIds.size;
        const mCount = selectedMapIds.size;
        const caCount = selectedCacheIds.size;
        const pCount = selectedProcessIds.size;
        const totalCount = cCount + oCount + profCount + mCount + caCount + pCount;
        
        if (migrateSelectionCount) {
            migrateSelectionCount.textContent = `${totalCount} item${totalCount === 1 ? '' : 's'} selected`;
            if (totalCount > 0) {
                migrateSelectionCount.classList.add('has-selected');
                const breakdown = [];
                if (pCount) breakdown.push(`${pCount} procs`);
                if (cCount) breakdown.push(`${cCount} conns`);
                if (oCount) breakdown.push(`${oCount} ops`);
                if (mCount) breakdown.push(`${mCount} maps`);
                if (caCount) breakdown.push(`${caCount} caches`);
                if (profCount) breakdown.push(`${profCount} profs`);
                migrateSelectionCount.title = `Breakdown: ${breakdown.join(', ')}`;
            } else {
                migrateSelectionCount.classList.remove('has-selected');
                migrateSelectionCount.title = 'No items selected';
            }
        }

        const folderVal = folderFilter ? folderFilter.value.trim() : '';

        if (totalCount > 0) {
            if (migrationModeBadge) {
                migrationModeBadge.textContent = `🎯 Targeted Component Mode (${totalCount})`;
                migrationModeBadge.className = 'mode-badge targeted-mode';
            }
            if (migrationIntentNote) {
                const parts = [];
                if (pCount) parts.push(`<strong>${pCount}</strong> process${pCount > 1 ? 'es' : ''}`);
                if (cCount) parts.push(`<strong>${cCount}</strong> connection${cCount > 1 ? 's' : ''}`);
                if (oCount) parts.push(`<strong>${oCount}</strong> operation${oCount > 1 ? 's' : ''}`);
                if (mCount) parts.push(`<strong>${mCount}</strong> map${mCount > 1 ? 's' : ''}`);
                if (caCount) parts.push(`<strong>${caCount}</strong> cache${caCount > 1 ? 's' : ''}`);
                if (profCount) parts.push(`<strong>${profCount}</strong> profile${profCount > 1 ? 's' : ''}`);
                migrationIntentNote.innerHTML = `🎯 <strong>Targeted Mode:</strong> Only the selected component(s) will be migrated to DB V2: ${parts.join(', ')}.`;
            }
            if (migrateBtn) {
                const btnText = migrateBtn.querySelector('.btn-text');
                if (btnText) btnText.textContent = `Execute DB V2 Migration (${totalCount} Selected Item${totalCount > 1 ? 's' : ''})`;
            }
        } else {
            if (migrationModeBadge) {
                if (folderVal) {
                    migrationModeBadge.textContent = `📁 Folder Mode ("${folderVal}")`;
                } else {
                    migrationModeBadge.textContent = '🌐 Account / All Mode';
                }
                migrationModeBadge.className = 'mode-badge folder-mode';
            }
            if (migrationIntentNote) {
                if (folderVal) {
                    migrationIntentNote.innerHTML = `📁 <strong>Folder Mode:</strong> No individual components selected. All legacy database components in folder "<strong>${escapeHtml(folderVal)}</strong>" will be migrated.`;
                } else {
                    migrationIntentNote.innerHTML = `🌐 <strong>Account Mode:</strong> No individual components or folders selected. All discovered legacy database components in the account will be migrated.`;
                }
            }
            if (migrateBtn) {
                const btnText = migrateBtn.querySelector('.btn-text');
                if (btnText) {
                    btnText.textContent = folderVal 
                        ? `Execute DB V2 Migration (Folder: ${folderVal})` 
                        : `Execute DB V2 Migration (All Discovered Components)`;
                }
            }
        }
    }

    if (folderFilter) {
        folderFilter.addEventListener('input', updateMigrationSelectionUI);
    }

    function isCompSelected(type, id) {
        if (type === 'connections' || type === 'connection') return selectedConnectionIds.has(id);
        if (type === 'operations' || type === 'operation') return selectedOperationIds.has(id);
        if (type === 'profiles' || type === 'profile') return selectedProfileIds.has(id);
        if (type === 'maps' || type === 'map') return selectedMapIds.has(id);
        if (type === 'caches' || type === 'cache') return selectedCacheIds.has(id);
        if (type === 'processes' || type === 'process') return selectedProcessIds.has(id);
        return false;
    }

    function setCompSelected(type, id, val) {
        let setRef = null;
        if (type === 'connections' || type === 'connection') setRef = selectedConnectionIds;
        else if (type === 'operations' || type === 'operation') setRef = selectedOperationIds;
        else if (type === 'profiles' || type === 'profile') setRef = selectedProfileIds;
        else if (type === 'maps' || type === 'map') setRef = selectedMapIds;
        else if (type === 'caches' || type === 'cache') setRef = selectedCacheIds;
        else if (type === 'processes' || type === 'process') setRef = selectedProcessIds;
        if (setRef) {
            if (val) setRef.add(id);
            else setRef.delete(id);
        }
    }

    function collectDescendantComponents(node) {
        const res = [];
        const cats = ['processes', 'connections', 'operations', 'profiles', 'maps', 'caches'];
        cats.forEach(cat => {
            (node.direct[cat] || []).forEach(item => {
                const id = item.componentId || item.id;
                if (id) res.push({ id, type: cat, name: item.name });
            });
        });
        Object.values(node.children || {}).forEach(child => {
            res.push(...collectDescendantComponents(child));
        });
        return res;
    }

    function renderMigrationProcessTree(scanData, searchQuery = '') {
        renderMigrationComponentTree(scanData, searchQuery);
    }

    function renderMigrationComponentTree(scanData, searchQuery = '') {
        if (!migrateProcessTree) return;
        if (!scanData || (
            (!scanData.processes || scanData.processes.length === 0) &&
            (!scanData.connections || scanData.connections.length === 0) &&
            (!scanData.operations || scanData.operations.length === 0) &&
            (!scanData.profiles || scanData.profiles.length === 0) &&
            (!scanData.maps || scanData.maps.length === 0) &&
            (!scanData.caches || scanData.caches.length === 0)
        )) {
            migrateProcessTree.innerHTML = `
                <div style="padding: 24px; text-align: center; color: var(--text-secondary);">
                    <em>No database components discovered yet. Run Discovery Scan in Tab 1 first.</em>
                </div>`;
            updateMigrationSelectionUI();
            return;
        }

        const query = (searchQuery || '').toLowerCase().trim();
        const rootFolders = buildHierarchicalTree(scanData, query);

        // Filter root folders based on active category filter
        const filteredFolders = rootFolders.filter(f => {
            if (migrateTypeFilter === 'all') return f.rollupCount > 0;
            return (f.rollup[migrateTypeFilter] || 0) > 0;
        });
        filteredFolders.sort((a, b) => a.name.localeCompare(b.name));

        if (filteredFolders.length === 0) {
            migrateProcessTree.innerHTML = `
                <div style="padding: 24px; text-align: center; color: var(--text-secondary);">
                    <div style="font-size: 1.1rem; margin-bottom: 6px;">🔍 No matching items found</div>
                    <div style="font-size: 0.85rem;">No components match "${escapeHtml(query)}" in filter "${escapeHtml(migrateTypeFilter)}".</div>
                </div>`;
            return;
        }

        migrateProcessTree.innerHTML = '';
        const fragment = document.createDocumentFragment();

        filteredFolders.forEach(folderNode => {
            const el = createMigrationFolderElement(folderNode, query, 0);
            if (el) fragment.appendChild(el);
        });

        migrateProcessTree.appendChild(fragment);
        updateMigrationSelectionUI();
    }

    function createMigrationFolderElement(folder, query, depth = 0) {
        const folderMatchingCount = (migrateTypeFilter === 'all') ? folder.rollupCount : (folder.rollup[migrateTypeFilter] || 0);
        if (folderMatchingCount === 0) return null;

        const childFolders = Object.values(folder.children || {}).filter(c => {
            return (migrateTypeFilter === 'all') ? c.rollupCount > 0 : ((c.rollup[migrateTypeFilter] || 0) > 0);
        });
        childFolders.sort((a, b) => a.name.localeCompare(b.name));
        const isMainFolder = depth === 0;
        const hasSubfolders = childFolders.length > 0;

        const allDescendants = collectDescendantComponents(folder);
        const filterDescendants = (migrateTypeFilter === 'all') ? allDescendants : allDescendants.filter(i => i.type === migrateTypeFilter);

        const folderEl = document.createElement('div');
        folderEl.className = isMainFolder ? 'main-folder-node' : 'subfolder-node';
        folderEl.style.marginBottom = isMainFolder ? '12px' : '6px';
        folderEl.style.background = '#ffffff';
        folderEl.style.borderRadius = isMainFolder ? '10px' : '6px';
        folderEl.style.border = isMainFolder ? '1px solid #cbd5e1' : '1px solid #e2e8f0';
        folderEl.style.overflow = 'hidden';

        // Header
        const header = document.createElement('div');
        header.className = isMainFolder ? 'main-folder-header' : 'subfolder-header';
        header.style.cursor = 'pointer';
        header.style.padding = isMainFolder ? '10px 14px' : '7px 10px';
        header.style.display = 'flex';
        header.style.justifyContent = 'space-between';
        header.style.alignItems = 'center';
        header.style.userSelect = 'none';
        header.style.background = isMainFolder ? '#ffffff' : '#f8fafc';

        // Check if all descendant matching items are checked
        const allChecked = filterDescendants.length > 0 && filterDescendants.every(i => isCompSelected(i.type, i.id));
        const someChecked = filterDescendants.some(i => isCompSelected(i.type, i.id));

        const badgeLabel = migrateTypeFilter === 'all' 
            ? `${folder.rollupCount} Items`
            : `${folder.rollup[migrateTypeFilter] || 0} ${migrateTypeFilter}`;

        header.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; max-width: 75%;">
                <input type="checkbox" class="folder-select-chk" title="Toggle select all ${filterDescendants.length} item(s) in this folder branch" ${allChecked ? 'checked' : ''} style="cursor: pointer; width: 15px; height: 15px; accent-color: #6c5ce7;">
                <span class="folder-chevron" style="display: inline-block; transition: transform 0.2s ease; font-size: 0.72rem; color: #6c5ce7;">▶</span>
                <span style="font-size: ${isMainFolder ? '0.98rem' : '0.85rem'}; font-weight: 700; color: #1e293b;">${isMainFolder ? '📁' : '📂'} ${highlightMatch(folder.name, query)}</span>
                <span style="font-size: 0.65rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; background: ${isMainFolder ? '#e0e7ff' : '#e2e8f0'}; color: ${isMainFolder ? '#4338ca' : '#475569'};">
                    ${isMainFolder ? 'Main Folder' : (depth === 1 ? 'Subfolder' : 'Sub-subfolder')}
                </span>
                <span style="font-size: 0.7rem; color: #64748b; font-family: monospace;">(${escapeHtml(folder.fullPath)})</span>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
                <span class="badge" style="font-size: 0.7rem; background: #e0e7ff; color: #4338ca;">${badgeLabel}</span>
            </div>
        `;

        const folderChk = header.querySelector('.folder-select-chk');
        if (someChecked && !allChecked) {
            folderChk.indeterminate = true;
        }

        folderChk.addEventListener('click', (e) => {
            e.stopPropagation();
            const shouldCheck = folderChk.checked;
            filterDescendants.forEach(i => {
                setCompSelected(i.type, i.id, shouldCheck);
            });

            // Sync visual checkboxes in DOM
            folderEl.querySelectorAll('.component-select-chk').forEach(cChk => {
                cChk.checked = shouldCheck;
                const node = cChk.closest('.process-tree-node');
                if (node) {
                    if (shouldCheck) node.classList.add('selected');
                    else node.classList.remove('selected');
                }
            });

            updateMigrationSelectionUI();
        });

        // Content
        const content = document.createElement('div');
        content.className = isMainFolder ? 'main-folder-content' : 'subfolder-content';
        content.style.display = 'none';
        content.style.padding = isMainFolder ? '10px 14px' : '6px 10px';
        content.style.background = isMainFolder ? '#fcfdfe' : '#ffffff';
        content.style.borderTop = '1px solid #e2e8f0';

        const chevron = header.querySelector('.folder-chevron');

        let isRendered = false;
        const renderContents = () => {
            if (isRendered) return;
            isRendered = true;

            // 1. Render nested subfolders
            if (hasSubfolders) {
                const subContainer = document.createElement('div');
                subContainer.className = 'folder-subfolders-container';
                subContainer.style.borderLeft = '2px dashed #cbd5e1';
                subContainer.style.paddingLeft = '12px';
                subContainer.style.marginLeft = '8px';
                subContainer.style.marginTop = '4px';
                subContainer.style.marginBottom = '8px';

                childFolders.forEach(subChild => {
                    const subEl = createMigrationFolderElement(subChild, query, depth + 1);
                    if (subEl) subContainer.appendChild(subEl);
                });

                content.appendChild(subContainer);
            }

            // 2. Render direct components
            const directContainer = document.createElement('div');
            directContainer.className = 'folder-direct-components-container';

            const categoriesToRender = [
                { key: 'processes', label: '🚀 Direct DB Processes', badge: 'process', badgeLabel: 'Process' },
                { key: 'connections', label: '🔌 Direct DB Connections', badge: 'connection', badgeLabel: 'Connection' },
                { key: 'operations', label: '⚙️ Direct DB Operations', badge: 'operation', badgeLabel: 'Operation' },
                { key: 'maps', label: '🗺️ Direct Maps', badge: 'map', badgeLabel: 'Map' },
                { key: 'caches', label: '💾 Direct Document Caches', badge: 'cache', badgeLabel: 'Cache' },
                { key: 'profiles', label: '📄 Direct DB Profiles', badge: 'profile', badgeLabel: 'Profile' }
            ];

            let hasAnyDirect = false;

            categoriesToRender.forEach(catMeta => {
                if (migrateTypeFilter !== 'all' && migrateTypeFilter !== catMeta.key) return;

                const items = folder.direct[catMeta.key] || [];
                if (items.length === 0) return;
                hasAnyDirect = true;

                const secHeader = document.createElement('div');
                secHeader.style.fontSize = '0.72rem';
                secHeader.style.fontWeight = '700';
                secHeader.style.color = '#334155';
                secHeader.style.margin = '8px 0 6px 0';
                secHeader.style.textTransform = 'uppercase';
                secHeader.style.letterSpacing = '0.4px';
                secHeader.textContent = `${catMeta.label} (${items.length}):`;
                directContainer.appendChild(secHeader);

                items.forEach(item => {
                    const cid = item.componentId || item.id;
                    const boomiUrl = getBoomiComponentUrl(cid);
                    const isChecked = isCompSelected(catMeta.key, cid);

                    const row = document.createElement('div');
                    row.className = `process-tree-node ${isChecked ? 'selected' : ''}`;
                    row.style.marginBottom = '6px';
                    row.style.padding = '7px 10px';
                    row.style.borderRadius = '6px';
                    row.style.background = '#ffffff';
                    row.style.border = '1px solid rgba(0,0,0,0.06)';
                    row.style.display = 'flex';
                    row.style.justifyContent = 'space-between';
                    row.style.alignItems = 'center';
                    row.style.cursor = 'pointer';

                    row.innerHTML = `
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <input type="checkbox" class="component-select-chk" data-comp-id="${cid}" data-comp-type="${catMeta.key}" data-comp-name="${escapeHtml(item.name)}" ${isChecked ? 'checked' : ''} style="cursor: pointer; width: 15px; height: 15px; accent-color: #6c5ce7;">
                            <span class="badge ${catMeta.badge}" style="font-size: 0.68rem;">${catMeta.badgeLabel}</span>
                            <a href="${boomiUrl}" target="_blank" rel="noopener noreferrer" class="component-link" title="Open '${escapeHtml(item.name)}' directly in Boomi Build tab" onclick="event.stopPropagation();" style="font-size: 0.85rem; font-weight: 600;">
                                ${highlightMatch(item.name, query)}
                                <svg style="width:11px; height:11px; vertical-align:middle; fill:currentColor;" viewBox="0 0 24 24"><path d="M14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3m-2 16H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7z"/></svg>
                            </a>
                        </div>
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <code style="font-size: 0.72rem; background: #f0edff; color: #6c5ce7; padding: 2px 6px; border-radius: 4px;">${cid}</code>
                        </div>
                    `;

                    const chk = row.querySelector('.component-select-chk');
                    chk.addEventListener('change', () => {
                        setCompSelected(catMeta.key, cid, chk.checked);
                        if (chk.checked) row.classList.add('selected');
                        else row.classList.remove('selected');

                        // Update parent folder checkbox state
                        const parentAllChecked = filterDescendants.every(i => isCompSelected(i.type, i.id));
                        const parentSomeChecked = filterDescendants.some(i => isCompSelected(i.type, i.id));
                        folderChk.checked = parentAllChecked;
                        folderChk.indeterminate = parentSomeChecked && !parentAllChecked;

                        updateMigrationSelectionUI();
                    });

                    // Clicking row toggles checkbox
                    row.addEventListener('click', (e) => {
                        if (e.target === chk || e.target.closest('a')) return;
                        chk.checked = !chk.checked;
                        chk.dispatchEvent(new Event('change'));
                    });

                    directContainer.appendChild(row);
                });
            });

            if (hasAnyDirect) {
                content.appendChild(directContainer);
            }
        };

        header.addEventListener('click', () => {
            const isExpanded = content.style.display !== 'none';
            if (isExpanded) {
                content.style.display = 'none';
                chevron.style.transform = 'rotate(0deg)';
            } else {
                content.style.display = 'block';
                chevron.style.transform = 'rotate(90deg)';
                renderContents();
            }
        });

        // Auto-expand Main Folder (depth 0) or on search query
        if (depth === 0 || query) {
            content.style.display = 'block';
            chevron.style.transform = 'rotate(90deg)';
            renderContents();
        }

        folderEl.appendChild(header);
        folderEl.appendChild(content);
        return folderEl;
    }

    // Tab 2 Category Filter Buttons
    document.querySelectorAll('.migrate-cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.migrate-cat-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            migrateTypeFilter = btn.dataset.type || 'all';
            const q = migrateProcessSearch ? migrateProcessSearch.value.trim() : '';
            renderMigrationComponentTree(currentScanData, q);
        });
    });

    // Component Search Input Event
    if (migrateProcessSearch) {
        migrateProcessSearch.addEventListener('input', () => {
            const q = migrateProcessSearch.value.trim();
            if (migrateSearchClear) {
                if (q) migrateSearchClear.classList.remove('hidden');
                else migrateSearchClear.classList.add('hidden');
            }
            renderMigrationComponentTree(currentScanData, q);
        });
    }

    // Clear Search Button
    if (migrateSearchClear) {
        migrateSearchClear.addEventListener('click', () => {
            migrateProcessSearch.value = '';
            migrateSearchClear.classList.add('hidden');
            renderMigrationComponentTree(currentScanData, '');
            migrateProcessSearch.focus();
        });
    }

    // Select All Visible Components Button
    if (migrateSelectAllBtn) {
        migrateSelectAllBtn.addEventListener('click', () => {
            if (!migrateProcessTree) return;
            const visibleChks = migrateProcessTree.querySelectorAll('.component-select-chk');
            visibleChks.forEach(chk => {
                const cid = chk.dataset.compId;
                const ctype = chk.dataset.compType;
                if (cid && ctype) {
                    chk.checked = true;
                    setCompSelected(ctype, cid, true);
                    const row = chk.closest('.process-tree-node');
                    if (row) row.classList.add('selected');
                }
            });
            migrateProcessTree.querySelectorAll('.folder-select-chk').forEach(fChk => {
                fChk.checked = true;
                fChk.indeterminate = false;
            });
            updateMigrationSelectionUI();
            showToast(`Selected ${visibleChks.length} visible component(s)`);
        });
    }

    // Clear All Selection Button
    if (migrateClearAllBtn) {
        migrateClearAllBtn.addEventListener('click', () => {
            selectedProcessIds.clear();
            selectedConnectionIds.clear();
            selectedOperationIds.clear();
            selectedProfileIds.clear();
            selectedMapIds.clear();
            selectedCacheIds.clear();
            if (migrateProcessTree) {
                migrateProcessTree.querySelectorAll('.component-select-chk').forEach(chk => {
                    chk.checked = false;
                    const row = chk.closest('.process-tree-node');
                    if (row) row.classList.remove('selected');
                });
                migrateProcessTree.querySelectorAll('.folder-select-chk').forEach(fChk => {
                    fChk.checked = false;
                    fChk.indeterminate = false;
                });
            }
            updateMigrationSelectionUI();
            showToast("Cleared all component selections");
        });
    }

    // Auto-render migration tree when switching to Tab 2 if data is loaded
    if (navTabs.migrate) {
        navTabs.migrate.addEventListener('click', () => {
            if (currentScanData && (!migrateProcessTree.querySelector('.main-folder-node') && !migrateProcessTree.querySelector('.subfolder-node'))) {
                renderMigrationComponentTree(currentScanData, '');
            }
            updateMigrationSelectionUI();
        });
    }

    // 3. Migration execution using stream
    migrateBtn.addEventListener('click', async () => {
        const credentials = getCredentials();
        if (!credentials.username || !credentials.api_token || !credentials.account_id) {
            showToast("⚠️ Missing credentials. Please enter your Boomi Username, API Token, and Account ID first.");
            validateBtn.focus();
            return;
        }
        if (!validateBranchPreflight(credentials.branch)) {
            return;
        }

        setSpinner(migrateBtn, true);
        consoleSection.classList.remove('hidden');
        terminalLog.innerHTML = `<div class="log-line system">Initializing migration connection on branch '${escapeHtml(credentials.branch)}'...</div>`;
        
        const payload = {
            credentials: credentials,
            ai_provider: providerInput.value,
            ai_key: keyInput.value,
            folder_filter: folderFilter.value.trim(),
            selected_process_ids: Array.from(selectedProcessIds),
            selected_connection_ids: Array.from(selectedConnectionIds),
            selected_operation_ids: Array.from(selectedOperationIds),
            selected_profile_ids: Array.from(selectedProfileIds),
            selected_map_ids: Array.from(selectedMapIds),
            selected_cache_ids: Array.from(selectedCacheIds),
            session_id: tabSessionId
        };
        
        try {
            const response = await fetch('/api/migrate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || `Migration request rejected (HTTP ${response.status})`);
            }
            if (!response.body) {
                throw new Error("Failed to read server event stream");
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // Keep partial line in buffer
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.slice(6).trim();
                        if (!jsonStr) continue;
                        
                        try {
                            const eventData = JSON.parse(jsonStr);
                            if (eventData.log) {
                                appendLogLine(eventData.log, eventData.status);
                            }
                            
                            // Check if final payload carries migration summary report
                            if (eventData.status === 'success' && eventData.summary) {
                                renderSummaryReport(eventData.summary);
                                navTabs.report.disabled = false;
                                showToast("Migration completed successfully!");
                            }
                        } catch (e) {
                            console.error("Error parsing log line:", e);
                        }
                    }
                }
            }
        } catch (error) {
            appendLogLine(`Migration Error: ${error.message}`, 'error');
            showToast("Migration failed");
        } finally {
            setSpinner(migrateBtn, false);
        }
    });

    function appendLogLine(text, status) {
        const line = document.createElement('div');
        line.className = 'log-line';
        if (status === 'error' || text.toLowerCase().includes('fail') || text.toLowerCase().includes('error')) {
            line.classList.add('error');
        } else if (status === 'success' || text.includes('Completed Successfully')) {
            line.classList.add('success');
        } else if (text.startsWith('---') || text.includes('V2 Connection')) {
            line.classList.add('system');
        } else {
            line.classList.add('info');
        }
        line.textContent = text;
        terminalLog.appendChild(line);
        terminalLog.scrollTop = terminalLog.scrollHeight;
    }

    function renderSummaryReport(summary) {
        reportSummaryBody.innerHTML = '';
        summary.forEach(item => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><span class="badge ${item.type.toLowerCase()}">${item.type}</span></td>
                <td>${item.old_name}</td>
                <td><code>${item.old_id}</code></td>
                <td>${item.new_name}</td>
                <td><code>${item.new_id}</code></td>
                <td style="color: var(--accent-success); font-weight:600;">${item.status}</td>
            `;
            reportSummaryBody.appendChild(row);
        });
    }

    // Download Final Report
    downloadMigReportBtn.addEventListener('click', () => {
        const creds = getCredentials();
        const accId = encodeURIComponent(creds.account_id || '');
        window.open(`/api/download-migration-report?session_id=${tabSessionId}&account_id=${accId}`, '_blank');
    });
});
