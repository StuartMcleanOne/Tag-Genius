// === STATE MANAGEMENT ===
const state = {
    currentView: 'deck',
    currentMode: 'tag',
    currentLevel: 3,
    uploadedFile: null,
    isProcessing: false,
    jobId: null,
    timerInterval: null,
    scanInterval: null,
    pollInterval: null,
    startTime: null
};

const API_BASE_URL = 'http://127.0.0.1:5001';

// === DOM ELEMENTS ===
const video = document.getElementById('vj-background');
const dropZone = document.getElementById('drop-zone');
const fileDisplay = document.getElementById('file-display');
const fileInput = document.getElementById('file-input');
const resultPanel = document.getElementById('result-panel');
const resultText = document.getElementById('result-text');
const downloadBtn = document.getElementById('download-btn');
const statusLed = document.getElementById('status-led');
const progressFill = document.getElementById('progress-fill');
const progressCounter = document.getElementById('progress-counter');
const deckClock = document.getElementById('deck-clock');
const playBtn = document.getElementById('play-btn');
const stopBtn = document.getElementById('stop-btn');
const loadBtn = document.getElementById('load-btn');
const eqSection = document.getElementById('eq-section');

// === VIEW SWITCHING ===
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        switchView(btn.dataset.view);
    });
});

function switchView(view) {
    state.currentView = view;

    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });

    // Update view containers
    document.querySelectorAll('.view-container').forEach(container => {
        container.classList.remove('active');
    });
    document.getElementById(`view-${view}`).classList.add('active');

    // Load data for specific views
    if (view === 'logs') {
        loadLogs();
    } else if (view === 'workspace') {
        loadWorkspace();
    }
}

// === MODE SWITCHING ===
document.querySelectorAll('.btn-mode').forEach(btn => {
    btn.addEventListener('click', () => {
        setMode(btn.dataset.mode);
    });
});

function setMode(mode) {
    state.currentMode = mode;

    // Update mode buttons
    document.querySelectorAll('.btn-mode').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    // Update EQ section
    if (mode === 'tag') {
        eqSection.classList.remove('mode-locked');
        updateVisualizerState(state.currentLevel);
    } else {
        eqSection.classList.add('mode-locked');
        document.querySelectorAll('.dash').forEach(dash => {
            dash.classList.remove('active');
        });
    }
}

// === DETAIL LEVEL SWITCHING ===
document.querySelectorAll('.level-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (state.currentMode !== 'tag') return;

        const level = parseInt(btn.dataset.level);
        setDetailLevel(level);
    });
});

function setDetailLevel(level) {
    state.currentLevel = level;

    // Update level buttons
    document.querySelectorAll('.level-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.level) === level);
    });

    updateVisualizerState(level);
}

function updateVisualizerState(level) {
    const maxDashes = level - 1;

    document.querySelectorAll('.viz-group').forEach(group => {
        const dashes = group.querySelectorAll('.dash');
        dashes.forEach((dash, idx) => {
            dash.classList.toggle('active', idx < maxDashes);
        });
    });
}

// === SCANNING ANIMATION ===
function startScanning() {
    if (state.scanInterval) clearInterval(state.scanInterval);

    let step = 0;
    const dashes = Array.from(document.querySelectorAll('.dash'));

    state.scanInterval = setInterval(() => {
        dashes.forEach(d => d.classList.remove('active'));

        // Light up 3 dashes at a time
        for (let i = 0; i < 3; i++) {
            if (dashes[step + i]) {
                dashes[step + i].classList.add('active');
            }
        }

        step++;
        if (step >= dashes.length) step = 0;
    }, 200);
}

function stopScanning() {
    if (state.scanInterval) {
        clearInterval(state.scanInterval);
        state.scanInterval = null;
    }

    if (state.currentMode === 'tag') {
        updateVisualizerState(state.currentLevel);
    }
}

// === FILE HANDLING ===
dropZone.addEventListener('click', () => {
    fileInput.click();
});

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '#fff';
});

dropZone.addEventListener('dragleave', () => {
    dropZone.style.borderColor = '';
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '';
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
        handleFile(e.target.files[0]);
    }
});

loadBtn.addEventListener('click', () => {
    fileInput.click();
});

function handleFile(file) {
    if (!file || !file.name.endsWith('.xml')) {
        alert('INVALID FILE - MUST BE XML');
        return;
    }

    state.uploadedFile = file;
    mountFile(file.name);
}

function mountFile(filename) {
    dropZone.classList.add('mounted');
    dropZone.querySelector('.drop-text-large').textContent = '[ DISK MOUNTED ]';
    dropZone.querySelector('.drop-text-small').textContent = 'READY';
    fileDisplay.textContent = `>> ${filename}`;
    fileDisplay.classList.remove('hidden');
    resultPanel.classList.remove('visible');

    // RESET PROGRESS FROM PREVIOUS JOB
    progressFill.style.width = '0%';
    progressCounter.textContent = '0 / 0';
}

// === JOB CONTROL ===
playBtn.addEventListener('click', startJob);
stopBtn.addEventListener('click', stopJob);

async function startJob() {
    if (!state.uploadedFile || state.isProcessing) return;

    // Start processing
    state.isProcessing = true;
    document.body.classList.add('job-running');
    video.play();

    playBtn.classList.add('active');
    statusLed.classList.add('active');

    startScanning();
    startTimer();

    // Prepare config based on mode
    let config = {};
    if (state.currentMode === 'tag') {
        const levelMap = {
            2: 'Essential',
            3: 'Recommended',
            4: 'Detailed'
        };
        config = { level: levelMap[state.currentLevel] };
    } else {
        config = { level: state.currentMode.charAt(0).toUpperCase() + state.currentMode.slice(1) };
    }

    // Upload file
    const formData = new FormData();
    formData.append('file', state.uploadedFile);
    formData.append('config', JSON.stringify(config));

    try {
        const response = await fetch(`${API_BASE_URL}/upload_library`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (response.status === 202 && data.job_id) {
            state.jobId = data.job_id;
            startPolling(data.job_id);
        } else {
            throw new Error('No job ID received');
        }
    } catch (error) {
        console.error('Job start failed:', error);
        handleError('UPLOAD FAILED - CHECK BACKEND');
    }
}

async function stopJob() {
    if (!state.jobId) return;

    try {
        await fetch(`${API_BASE_URL}/cancel_job/${state.jobId}`, {
            method: 'POST'
        });
    } catch (error) {
        console.error('Cancel failed:', error);
    }

    resetState();
}

// === JOB POLLING ===
function startPolling(jobId) {
    if (state.pollInterval) clearInterval(state.pollInterval);
    let lastProgressTime = Date.now();
    let noProgressTimeout = 30000; // 30 seconds

    state.pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/history`);
            const history = await response.json();
            const job = history.find(j => j.id === jobId);

            if (job) {
                if (job.result_data) {
                    lastProgressTime = Date.now(); // Reset timer when progress updates
                } else if (Date.now() - lastProgressTime > noProgressTimeout) {
                    clearInterval(state.pollInterval);
                    alert('ERROR: Job stalled. Check if Celery is running.');
                    resetState();
                    return;
                }

                updateProgress(job)

                if (job.status === 'Completed') {
                    clearInterval(state.pollInterval);
                    handleJobComplete(job);
                } else if (job.status === 'Failed') {
                    clearInterval(state.pollInterval);
                    handleJobFailed(job);
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
}

function updateProgress(job) {
    if (job.result_data) {
        try {
            const data = JSON.parse(job.result_data);
            if (data.current !== undefined && data.total !== undefined) {
                const percent = Math.round((data.current / data.total) * 100);
                progressFill.style.width = `${percent}%`;
                progressCounter.textContent = `${data.current} / ${data.total}`;
            }
        } catch (e) {
            // Invalid JSON, ignore
        }
    }
}

function handleJobComplete(job) {
    resetState();
    progressFill.style.width = '100%';

    // CHECK IF SPLIT JOB
    if (job.job_type === 'split') {
        // Parse the array of file paths from result_data
        try {
            const filePaths = JSON.parse(job.result_data);
            if (Array.isArray(filePaths) && filePaths.length > 0) {
                // Get just the filenames
                const filenames = filePaths.map(path => path.split('/').pop());

                // Save to localStorage
                localStorage.setItem('tagamp_workspace', JSON.stringify(filenames));

                // Show message
                alert(`Split complete! ${filenames.length} files created. Check WORKSPACE view.`);
            }
        } catch (e) {
            console.error('Failed to parse split results:', e);
        }
    } else {
        // NORMAL TAG JOB - show download panel
        const filename = job.output_file_path ? job.output_file_path.split('/').pop() : 'tagged_file.xml';
        resultText.textContent = `FILE READY: ${filename}`;
        resultPanel.classList.add('visible');
    }
}

function handleJobFailed(job) {
    resetState();
    handleError('JOB FAILED - CHECK LOGS');
}

function handleError(message) {
    resetState();
    alert(message);
}

function resetState() {
    state.isProcessing = false;
    state.jobId = null;

    document.body.classList.remove('job-running');
    video.pause();

    playBtn.classList.remove('active');
    statusLed.classList.remove('active');

    stopScanning();
    stopTimer();

    if (state.pollInterval) {
        clearInterval(state.pollInterval);
        state.pollInterval = null;
    }
}

// === TIMER ===
function startTimer() {
    state.startTime = Date.now();

    state.timerInterval = setInterval(() => {
        const elapsed = Date.now() - state.startTime;
        const seconds = Math.floor(elapsed / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);

        const timeString = `/${String(hours).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
        deckClock.textContent = timeString;
    }, 1000);
}

function stopTimer() {
    if (state.timerInterval) {
        clearInterval(state.timerInterval);
        state.timerInterval = null;
    }
    deckClock.textContent = '/00:00:00';
}

// === DOWNLOAD & RESET ===
downloadBtn.addEventListener('click', async () => {
    // Trigger download
    window.location.href = `${API_BASE_URL}/export_xml`;

    // Reset after brief delay
    setTimeout(() => {
        resetToInitial();
    }, 1000);
});

function resetToInitial() {
    state.uploadedFile = null;

    dropZone.classList.remove('mounted');
    dropZone.querySelector('.drop-text-large').textContent = '[ INSERT DISK ]';
    dropZone.querySelector('.drop-text-small').textContent = 'DRAG XML OR CLICK LOAD';
    fileDisplay.classList.add('hidden');
    fileDisplay.textContent = '';

    resultPanel.classList.remove('visible');
    progressFill.style.width = '0%';
    progressCounter.textContent = '0 / 0';
}

// === LOGS VIEW ===
async function loadLogs() {
    try {
        const response = await fetch(`${API_BASE_URL}/history`);
        const history = await response.json();

        const logsList = document.getElementById('logs-list');
        logsList.innerHTML = '';

        if (history.length === 0) {
            logsList.innerHTML = '<div style="color:#666; text-align:center; padding:20px;">NO JOBS YET</div>';
            return;
        }

        history.forEach(job => {
            const entry = document.createElement('div');
            entry.className = 'log-entry';

            const timestamp = new Date(job.timestamp).toLocaleTimeString();
            const jobType = job.job_type === 'tagging' ? '[TAG]' : '[SPLIT]';
            const filename = job.original_filename || 'unknown.xml';
            const status = job.status.toUpperCase();
            const statusColor = job.status === 'Completed' ? '#00ff00' :
                               job.status === 'Failed' ? '#ef4444' : '#FFB000';

            entry.innerHTML = `
                <span style="width: 120px;">${timestamp}</span>
                <span style="flex: 1; padding-left: 20px;">
                    <span class="job-type">${jobType}</span> ${filename}
                </span>
                <span style="width: 120px; text-align: right; color: ${statusColor};">${status}</span>
            `;

            logsList.appendChild(entry);
        });
    } catch (error) {
        console.error('Failed to load logs:', error);
        document.getElementById('logs-list').innerHTML = '<div style="color:#ef4444; text-align:center; padding:20px;">FAILED TO LOAD LOGS</div>';
    }
}

// === WORKSPACE VIEW ===
async function loadWorkspace() {
    const workspaceList = document.getElementById('workspace-list');

    // Check for split files in sessionStorage
    const splitFiles = localStorage.getItem('tagamp_workspace');
    if (!splitFiles) {
        workspaceList.innerHTML = '<div style="color:#666; text-align:center; padding:20px;">NO SPLIT FILES YET</div>';
        return;
    }

    try {
        const files = JSON.parse(splitFiles);
        workspaceList.innerHTML = '';

        files.forEach(filename => {
            const item = document.createElement('div');
            item.className = 'workspace-item';

            item.innerHTML = `
                <span>${filename}</span>
                <div class="workspace-actions">
                    <button class="workspace-btn" onclick="mountWorkspaceFile('${filename}')">TAG</button>
                    <button class="workspace-btn" onclick="downloadWorkspaceFile('${filename}')">DOWNLOAD</button>
                </div>
            `;

            workspaceList.appendChild(item);
        });
    } catch (error) {
        console.error('Failed to parse workspace files:', error);
        workspaceList.innerHTML = '<div style="color:#ef4444; text-align:center; padding:20px;">WORKSPACE DATA CORRUPTED</div>';
    }
}

// Workspace file actions (global functions for onclick)
window.mountWorkspaceFile = function(filename) {
    // Switch to deck view
    switchView('deck');

    // Set TAG mode
    setMode('tag');

    // Mount the file (visual only - would need actual file object for real upload)
    mountFile(filename);
};

window.downloadWorkspaceFile = function(filename) {
    window.location.href = `${API_BASE_URL}/download_workspace_file?file=${encodeURIComponent(filename)}`;
};

// === INITIALIZATION ===
document.addEventListener('DOMContentLoaded', () => {
    // Set initial visualizer state
    updateVisualizerState(3);

    // Check for workspace files on load
    const splitFiles = sessionStorage.getItem('taggedSplitFiles');
    if (splitFiles) {
        console.log('Workspace files available:', splitFiles);
    }
});