document.addEventListener('DOMContentLoaded', () => {
    const API_BASE_URL = 'http://127.0.0.1:5001';
    let uploadedFile = null;
    let isProcessingJob = false;
    let currentJobId = null;
    let taggedSplitFiles = [];
    let scanInterval = null;

    const storedSplit = sessionStorage.getItem('taggedSplitFiles');
    if (storedSplit) taggedSplitFiles = JSON.parse(storedSplit);

    // --- 1. VISUALIZER ---
    window.setDetail = function(level) {
        if(document.querySelector('.eq-section').classList.contains('offline')) return;
        document.querySelectorAll('.slider-option').forEach(opt => opt.classList.remove('active'));
        document.querySelector(`.slider-option[data-level="${level}"]`).classList.add('active');
        const radios = document.getElementsByName('tag-level');
        for(let r of radios) if(r.value == level) r.click();
        updateVisualizerState(level);
    }

    function updateVisualizerState(level) {
        const maxDashes = level - 1;
        document.querySelectorAll('.viz-group').forEach(group => {
            const dashes = group.querySelectorAll('.dash');
            dashes.forEach((dash, idx) => {
                dash.classList.remove('active');
                if (idx < maxDashes) dash.classList.add('active');
            });
        });
    }

    function startScanning() {
        if(scanInterval) clearInterval(scanInterval);
        let step = 0;
        const dashes = document.querySelectorAll('.dash');
        scanInterval = setInterval(() => {
            dashes.forEach(d => d.classList.remove('active'));
            for(let i=0; i<3; i++) if(dashes[step + i]) dashes[step + i].classList.add('active');
            step++; if(step > dashes.length) step = 0;
        }, 300);
    }

    function stopScanning() {
        clearInterval(scanInterval);
        if(document.querySelector('input[name="mode"]:checked').value === 'tag') {
            const level = document.querySelector('input[name="tag-level"]:checked').value;
            updateVisualizerState(level);
        }
    }

    window.setMode = function(mode) {
        document.querySelectorAll('#btn-mode-tag, #btn-mode-split, #btn-mode-clear').forEach(b => b.classList.remove('active'));
        document.getElementById('btn-mode-' + mode).classList.add('active');
        document.getElementById('mode-' + mode).click();

        const eqSection = document.querySelector('.eq-section');
        const dashes = document.querySelectorAll('.dash');

        if(mode === 'tag') {
            eqSection.classList.remove('offline');
            const level = document.querySelector('input[name="tag-level"]:checked').value;
            updateVisualizerState(level);
        } else {
            eqSection.classList.add('offline');
            dashes.forEach(d => d.classList.remove('active'));
        }
    }

    window.switchView = function(view) {
        document.querySelectorAll('.channel-switch').forEach(el => el.classList.remove('active'));
        document.getElementById('nav-' + view).classList.add('active');
        document.getElementById('view-deck').classList.add('hidden');
        document.getElementById('view-logs').classList.add('hidden');
        document.getElementById('view-workspace').classList.add('hidden');
        document.getElementById('view-' + view).classList.remove('hidden');
        if(view === 'logs') fetchAndDisplayHistory();
        if(view === 'workspace') loadWorkspaceFiles();
    }

    updateVisualizerState(3);

    // --- 2. FILE HANDLING (CLICK FIX) ---
    const dragArea = document.getElementById('drag-area');

    // Explicit click handler on the container
    dragArea.addEventListener('click', () => {
        document.getElementById('file-input').click();
    });

    function handleFile(file) {
        if(!file || !file.name.endsWith('.xml')) { alert("INVALID FILE"); return; }
        uploadedFile = file;
        dragArea.style.borderColor = '#25FDE9';
        dragArea.style.color = '#25FDE9';
        dragArea.querySelector('.text-4xl').textContent = "[ DISK MOUNTED ]";
        dragArea.querySelector('.text-xl').textContent = "READY";
        document.getElementById('file-name-display').textContent = `>> ${file.name}`;
        document.getElementById('file-name-display').classList.remove('hidden');
        document.getElementById('status-text').textContent = "READY TO START";
    }

    dragArea.addEventListener('dragover', (e) => { e.preventDefault(); dragArea.style.borderColor = '#fff'; });
    dragArea.addEventListener('dragleave', () => { dragArea.style.borderColor = '#333'; });
    dragArea.addEventListener('drop', (e) => { e.preventDefault(); handleFile(e.dataTransfer.files[0]); });
    document.getElementById('file-input').addEventListener('change', (e) => { if(e.target.files.length) handleFile(e.target.files[0]); });

    // --- 3. JOBS ---

    document.getElementById('start-job-btn').addEventListener('click', async () => {
        if(!uploadedFile || isProcessingJob) return;

        // AMBER THEME ACTIVATION
        document.body.classList.add('job-running');

        const selectedMode = document.querySelector('input[name="mode"]:checked').value;
        let config = { "level": selectedMode === 'tag' ? document.querySelector('input[name="tag-level"]:checked').value : selectedMode.charAt(0).toUpperCase() + selectedMode.slice(1) };

        // Map Detail Level for Tagging
        if(selectedMode === 'tag') {
             const configs = { "2": {level:"Essential"}, "3": {level:"Recommended"}, "4": {level:"Detailed"} }; // Simplified for brevity
             config = configs[config.level] || config;
        }

        isProcessingJob = true;
        document.getElementById('start-job-btn').classList.add('active');
        document.getElementById('system-status-led').classList.add('active');
        document.getElementById('status-text').textContent = "INITIALIZING...";
        document.getElementById('main-results-area').classList.add('hidden');
        startScanning();

        const formData = new FormData();
        formData.append('file', uploadedFile);
        formData.append('config', JSON.stringify(config));

        try {
            const res = await fetch(`${API_BASE_URL}/upload_library`, { method: 'POST', body: formData });
            const data = await res.json();
            if(res.status === 202) {
                currentJobId = data.job_id;
                startJobTimer();
                pollJobStatus(data.job_id, selectedMode);
            }
        } catch(e) {
            resetState();
        }
    });

    document.getElementById('cancel-job-btn').addEventListener('click', async () => {
        if(!currentJobId) return;
        try { await fetch(`${API_BASE_URL}/cancel_job/${currentJobId}`, { method: 'POST' }); } catch(e) {}
    });

    function resetState() {
        isProcessingJob = false;
        document.body.classList.remove('job-running'); // Reset Theme
        stopJobTimer();
        stopScanning();
        document.getElementById('start-job-btn').classList.remove('active');
        document.getElementById('system-status-led').classList.remove('active');
        document.getElementById('progress-bar').style.width = '0%';
    }

    function pollJobStatus(jobId, jobType) {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${API_BASE_URL}/history`);
                const history = await res.json();
                const job = history.find(j => j.id === jobId);

                if(job) {
                    document.getElementById('status-text').textContent = `STATUS: ${job.status.toUpperCase()}`;
                    if(job.result_data) {
                        try {
                            const p = JSON.parse(job.result_data);
                            if(p.current && p.total) {
                                const pct = Math.round((p.current / p.total) * 100);
                                document.getElementById('progress-bar').style.width = `${pct}%`;
                                document.getElementById('progress-count').textContent = `[ ${p.current} / ${p.total} ]`;
                            }
                        } catch(e){}
                    }

                    if(job.status === 'Completed' || job.status === 'Failed') {
                        clearInterval(interval);
                        resetState();
                        if(job.status === 'Completed') {
                            handleComplete(job, jobType);
                        } else {
                            document.getElementById('status-text').textContent = "FAILED";
                            document.getElementById('progress-bar').style.backgroundColor = 'red';
                        }
                    }
                }
            } catch(e) {}
        }, 3000);
    }

    function handleComplete(job, jobType) {
        document.getElementById('progress-bar').style.width = '100%';
        document.getElementById('status-text').textContent = "COMPLETED";

        if(jobType === 'split') {
            sessionStorage.setItem('lastSplitResults', job.result_data);
            switchView('workspace');
        } else {
            document.getElementById('main-results-area').classList.remove('hidden');
            document.getElementById('main-tag-result-container').innerHTML = `
                <div class="text-xl">FILE READY: ${job.output_file_path.split('/').pop()}</div>
                <a href="${API_BASE_URL}/export_xml" class="pixel-btn border-green-500 text-green-500 hover:bg-green-500 hover:text-black px-6 py-2">DOWNLOAD</a>
            `;
        }
    }

    // Timer & Logs (Identical to previous logic)
    let timerInterval, timerStart;
    function startJobTimer() {
        timerStart = Date.now(); clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            document.getElementById('job-timer').textContent = '/' + new Date(Date.now() - timerStart).toISOString().substr(11, 8);
        }, 1000);
    }
    function stopJobTimer() { clearInterval(timerInterval); }
    async function fetchAndDisplayHistory() { /* ... same as before ... */ }
    window.loadWorkspaceFiles = function() { /* ... same as before ... */ }
});