// --- Wait for the DOM to be ready ---
document.addEventListener('DOMContentLoaded', () => {

    // --- 1. GLOBAL STATE & CONFIG ---
    let uploadedFile = null;
    let isProcessingJob = false;
    let currentJobId = null;  // Track current job ID for cancellation
    const API_BASE_URL = 'http://127.0.0.1:5001';

    const tagConfigurations = {
        "0": { "level": "Split" },
        "1": { "level": "Clear" },
        "2": { "level": "Essential", "sub_genre": 1, "energy_vibe": 1, "situation_environment": 1, "components": 1, "time_period": 1 },
        "3": { "level": "Recommended", "sub_genre": 2, "energy_vibe": 2, "situation_environment": 2, "components": 2, "time_period": 1 },
        "4": { "level": "Detailed", "sub_genre": 3, "energy_vibe": 3, "situation_environment": 3, "components": 3, "time_period": 1 }
    };

    // --- 2. GET ALL DOM ELEMENTS ---
    const dragArea = document.getElementById('drag-area');
    const fileInput = document.getElementById('file-input');
    const startJobBtn = document.getElementById('start-job-btn');
    const cancelJobBtn = document.getElementById('cancel-job-btn');
    const statusPanel = document.getElementById('status-panel');
    const statusText = document.getElementById('status-text');
    const vjBackground = document.getElementById('vj-background');

    // UI Areas
    const mainUploadArea = document.getElementById('main-upload-area');
    const mainResultsArea = document.getElementById('main-results-area');

    // Main Controls
    const mainControls = document.getElementById('main-controls');
    const modeRadios = document.querySelectorAll('input[name="mode"]');

    // Dynamic Panels
    const taggingLevelOptions = document.getElementById('tagging-level-options');
    const splitDescription = document.getElementById('split-description');
    const clearDescription = document.getElementById('clear-description');

    // Tag Preview Panels
    const tagLevelRadios = document.querySelectorAll('input[name="tag-level"]');
    const essentialPreview = document.getElementById('essential-preview');
    const recommendedPreview = document.getElementById('recommended-preview');
    const detailedPreview = document.getElementById('detailed-preview');

    // Main Results
    const mainResultsTitle = document.getElementById('main-results-title');
    const mainTagResultContainer = document.getElementById('main-tag-result-container');

    // Progress elements
    const statusContainer = document.getElementById('status-container');
    const progressBar = document.getElementById('progress-bar');
    const progressCount = document.getElementById('progress-count');
    const statusTextProgress = document.getElementById('status-text');
    const statusState = document.getElementById('status-state');

    // --- 3. HELPER FUNCTIONS ---

    function setVideoProcessing(isProcessing) {
        if (!vjBackground) return;
        if (isProcessing) {
            vjBackground.playbackRate = 1.0;
            vjBackground.play();
            vjBackground.classList.remove('paused');
        } else {
            vjBackground.pause();
            vjBackground.classList.add('paused');
        }
    }

    async function logAction(description) {
        try {
            await fetch(`${API_BASE_URL}/log_action`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action_description: description }),
            });
        } catch (error) {
            console.error('Failed to log action:', error);
        }
    }

    function resetUiToDefault() {
        mainUploadArea.classList.remove('hidden');
        mainResultsArea.classList.add('hidden');
        if (statusPanel) statusPanel.classList.add('hidden');

        dragArea.innerHTML = `<p class="text-sm text-blue-600 font-medium">Drag & drop your XML file here</p><p class="text-xs text-gray-500 mt-1">or click to browse</p>`;
        dragArea.style.borderStyle = 'dashed';

        uploadedFile = null;
        startJobBtn.disabled = true;

        document.getElementById('mode-tag').checked = true;
        document.getElementById('level-recommended').checked = true;
        updateControls();
    }

    function setDragAreaToFileSelected(fileName) {
        dragArea.innerHTML = `<p class="text-sm font-medium text-white">File Selected:</p><p class="text-xs text-gray-300 mt-1">${fileName}</p>`;
        dragArea.style.borderStyle = 'solid';
        startJobBtn.disabled = false;
    }

    function handleFile(file) {
        if (!file || !file.name.endsWith('.xml')) {
            alert("Only .xml files are allowed.");
            return;
        }

        uploadedFile = file;
        setDragAreaToFileSelected(uploadedFile.name);
        mainResultsArea.classList.add('hidden');
        if (statusPanel) statusPanel.classList.add('hidden');
        logAction(`User selected file: ${uploadedFile.name}`);
    }

    function updateTagPreview() {
        const selectedLevel = document.querySelector('input[name="tag-level"]:checked').value;

        essentialPreview.classList.add('hidden');
        recommendedPreview.classList.add('hidden');
        detailedPreview.classList.add('hidden');

        if (selectedLevel === '2') {
            essentialPreview.classList.remove('hidden');
        } else if (selectedLevel === '3') {
            recommendedPreview.classList.remove('hidden');
        } else if (selectedLevel === '4') {
            detailedPreview.classList.remove('hidden');
        }
    }

    function updateControls() {
        const selectedMode = document.querySelector('input[name="mode"]:checked').value;

        taggingLevelOptions.classList.add('hidden');
        splitDescription.classList.add('hidden');
        clearDescription.classList.add('hidden');

        if (selectedMode === 'tag') {
            taggingLevelOptions.classList.remove('hidden');
            updateTagPreview();
            startJobBtn.textContent = 'Start Tagging';
        } else if (selectedMode === 'split') {
            splitDescription.classList.remove('hidden');
            startJobBtn.textContent = 'Start Split';
        } else if (selectedMode === 'clear') {
            clearDescription.classList.remove('hidden');
            startJobBtn.textContent = 'Start Clear';
        }

        startJobBtn.disabled = (uploadedFile === null);
    }

        function showStatus(message) {
            // Hide start button, show progress
            startJobBtn.classList.add('hidden');
            const progressContainer = document.getElementById('progress-container');
            if (progressContainer) {
                progressContainer.classList.remove('hidden');
            }

            const progressText = document.getElementById('progress-text');
            if (progressText) progressText.textContent = message;

            if (mainControls) {
                mainControls.style.pointerEvents = 'none';
                mainControls.style.opacity = '0.5';
            }

            setVideoProcessing(true);
        }

        function hideStatus() {
            // Show start button, hide progress
            startJobBtn.classList.remove('hidden');
            const progressContainer = document.getElementById('progress-container');
            if (progressContainer) {
                progressContainer.classList.add('hidden');
            }

            const progressBar = document.getElementById('progress-bar');
            if (progressBar) progressBar.style.width = '0%';

            startJobBtn.disabled = (uploadedFile === null);
            updateControls();

            if (mainControls) {
                mainControls.style.pointerEvents = 'auto';
                mainControls.style.opacity = '1';
            }

            setVideoProcessing(false);
        }

    async function cancelCurrentJob() {
        if (!currentJobId) {
            console.log('No active job to cancel');
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/cancel_job/${currentJobId}`, {
                method: 'POST'
            });

            if (response.ok) {
                console.log('Job cancelled successfully');
                logAction(`User cancelled job ID ${currentJobId}`);
            }
        } catch (error) {
            console.error('Failed to cancel job:', error);
        }

        // Clear polling intervals
        if (window.pollingIntervalId) {
            clearInterval(window.pollingIntervalId);
        }
        if (window.splitPollingIntervalId) {
            clearInterval(window.splitPollingIntervalId);
        }

        // Reset state
        currentJobId = null;
        isProcessingJob = false;
        hideStatus();
        if (statusText) statusText.textContent = 'Job cancelled by user.';
    }

    function displayMainTagResult(jobDisplayName, isClearJob = false) {
        mainResultsTitle.textContent = isClearJob ? 'Clear Complete!' : 'Tagging Complete!';
        mainTagResultContainer.innerHTML = '';
        hideStatus();

        const message = document.createElement('p');
        message.className = 'text-sm text-gray-700 mb-4';
        message.textContent = `Your library "${jobDisplayName}" has been successfully ${isClearJob ? 'cleared' : 'tagged'}.`;

        const downloadButton = document.createElement('a');
        downloadButton.href = `${API_BASE_URL}/export_xml`;
        downloadButton.className = 'inline-block px-6 py-2 bg-green-600 text-white font-semibold rounded-full shadow-md hover:bg-green-700';
        downloadButton.textContent = `Download ${isClearJob ? 'Cleared' : 'Tagged'} Library`;
        downloadButton.setAttribute('download', '');

        mainTagResultContainer.appendChild(message);
        mainTagResultContainer.appendChild(downloadButton);

        mainResultsArea.classList.remove('hidden');
    }

    // --- 4. EVENT LISTENERS ---

    dragArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        dragArea.classList.add('active');
    });

    dragArea.addEventListener('dragleave', () => {
        dragArea.classList.remove('active');
    });

    dragArea.addEventListener('drop', (e) => {
        e.preventDefault();
        dragArea.classList.remove('active');
        if (e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    dragArea.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    });

    modeRadios.forEach(radio => radio.addEventListener('change', updateControls));
    tagLevelRadios.forEach(radio => radio.addEventListener('change', updateTagPreview));

    // Only add cancel listener if button exists
    if (cancelJobBtn) {
        cancelJobBtn.addEventListener('click', cancelCurrentJob);
    }

    // --- 5. MAIN "START" BUTTON LOGIC ---

    startJobBtn.addEventListener('click', async () => {
        if (!uploadedFile) return;

        if (isProcessingJob) {
            alert('Please wait for the current job to finish.');
            return;
        }

        const selectedMode = document.querySelector('input[name="mode"]:checked').value;
        let config;
        let jobType;

        if (selectedMode === 'tag') {
            const level = document.querySelector('input[name="tag-level"]:checked').value;
            config = { ...tagConfigurations[level] };
            jobType = 'tag';
        } else if (selectedMode === 'split') {
            config = { ...tagConfigurations["0"] };
            jobType = 'split';
        } else if (selectedMode === 'clear') {
            config = { ...tagConfigurations["1"] };
            jobType = 'clear';
        } else {
            return;
        }

        logAction(`User clicked 'Start' for job type: ${jobType} (Level: ${config.level})`);
        showStatus('Dispatching Job...');
        isProcessingJob = true;

        const formData = new FormData();
        formData.append('file', uploadedFile);
        formData.append('config', JSON.stringify(config));

        try {
            const response = await fetch(`${API_BASE_URL}/upload_library`, {
                method: 'POST',
                body: formData,
            });
            const result = await response.json();

            if (response.status === 202 && result.job_id) {
                currentJobId = result.job_id;  // Store job ID for cancellation
                if (jobType === 'split') {
                    pollSplitJobStatus(result.job_id);
                } else {
                    pollJobStatus(result.job_id, { isClearJob: (jobType === 'clear') });
                }
                logAction(`Job started successfully with ID ${result.job_id} for ${uploadedFile.name}`);
            } else {
                throw new Error(result.error || 'Failed to start job');
            }
        } catch (error) {
            console.error('Upload failed:', error);
            isProcessingJob = false;
            hideStatus();
            if (statusText) statusText.textContent = `Upload failed: ${error.message}. Is the server running?`;
            if (statusPanel) statusPanel.classList.remove('hidden');
            logAction(`Job failed to start: ${error.message}`);
        }
    });

    // --- 6. POLLING FUNCTIONS ---

    function pollJobStatus(jobIdToTrack, options = {}) {
        const { isClearJob = false } = options;
        let pollAttempts = 0;
        const MAX_POLLS = 120;

        if (window.pollingIntervalId) clearInterval(window.pollingIntervalId);

        window.pollingIntervalId = setInterval(async () => {
            if (pollAttempts++ > MAX_POLLS) {
                clearInterval(window.pollingIntervalId);
                isProcessingJob = false;
                hideStatus();
                if (statusText) statusText.textContent = "Job timed out after 10 minutes. Please check server.";
                if (statusPanel) statusPanel.classList.remove('hidden');
                logAction(`Job ${jobIdToTrack} timed out after ${MAX_POLLS} polling attempts.`);
                return;
            }

            try {
                const response = await fetch(`${API_BASE_URL}/history`);
                if (!response.ok) throw new Error('Failed to fetch history');
                const history = await response.json();
                const currentJob = history.find(job => job.id === jobIdToTrack);

                if (currentJob) {
                    const jobName = currentJob.job_display_name;
                    const trackCount = currentJob.track_count || 0;

                    // Update progress container text
                    if (statusTextProgress) {
                        statusTextProgress.textContent = `Processing ${jobName}...`;
                    }

                    // Update state indicator
                    if (statusState) {
                        statusState.textContent = currentJob.status;
                    }

                    // Update progress count display
                    if (progressCount && trackCount > 0) {
                        progressCount.textContent = `${trackCount} tracks`;
                    } else {
                        progressCount.textContent = 'Processing...';
                    }

                    // Show indeterminate progress (full bar pulsing)
                    if (progressBar) {
                        progressBar.style.width = '100%';
                    }

                    if (currentJob.status === 'Completed' || currentJob.status === 'Failed') {
                        clearInterval(window.pollingIntervalId);
                        isProcessingJob = false;

                        if (currentJob.status === 'Completed') {
                            logAction(`Job completed for ${jobName}`);
                            hideStatus();
                            displayMainTagResult(jobName, isClearJob);
                            setDragAreaToFileSelected(uploadedFile.name);
                        } else {
                            logAction(`Job failed for ${jobName}`);
                            hideStatus();
                            if (statusText) statusText.textContent = `Job '${jobName}' failed. Check logs.`;
                            if (statusPanel) statusPanel.classList.remove('hidden');
                        }
                    }
                }
            } catch (error) {
                console.error('Polling error:', error);
                clearInterval(window.pollingIntervalId);
                isProcessingJob = false;
                hideStatus();
                if (statusText) statusText.textContent = `Polling failed: ${error.message}`;
                if (statusPanel) statusPanel.classList.remove('hidden');
            }
        }, 5000);
    }

    function pollSplitJobStatus(jobIdToTrack) {
        let pollAttempts = 0;
        const MAX_POLLS = 120;

        if (window.splitPollingIntervalId) clearInterval(window.splitPollingIntervalId);

        window.splitPollingIntervalId = setInterval(async () => {
            if (pollAttempts++ > MAX_POLLS) {
                clearInterval(window.splitPollingIntervalId);
                isProcessingJob = false;
                hideStatus();
                if (statusText) statusText.textContent = "Split job timed out after 10 minutes. Please check server.";
                if (statusPanel) statusPanel.classList.remove('hidden');
                logAction(`Split job ${jobIdToTrack} timed out after ${MAX_POLLS} polling attempts.`);
                return;
            }

            try {
                const response = await fetch(`${API_BASE_URL}/history`);
                if (!response.ok) throw new Error('Failed to fetch history');
                const history = await response.json();
                const currentJob = history.find(job => job.id === jobIdToTrack);

                if (currentJob) {
                    showStatus(`Processing ${currentJob.job_display_name}... (Status: ${currentJob.status})`);

                    if (currentJob.status === 'Completed' || currentJob.status === 'Failed') {
                        clearInterval(window.splitPollingIntervalId);
                        isProcessingJob = false;

                        if (currentJob.status === 'Completed' && currentJob.result_data) {
                            // Save split results and redirect to workspace
                            sessionStorage.setItem('lastSplitResults', currentJob.result_data);
                            sessionStorage.setItem('taggedSplitFiles', JSON.stringify([]));
                            logAction(`Split job ${jobIdToTrack} completed successfully. Redirecting to workspace.`);
                            window.location.href = 'workspace.html';
                        } else {
                            hideStatus();
                            if (statusText) statusText.textContent = `Job '${currentJob.job_display_name}' failed. Check logs.`;
                            if (statusPanel) statusPanel.classList.remove('hidden');
                            logAction(`Split job ${jobIdToTrack} failed.`);
                        }
                    }
                }
            } catch (error) {
                console.error('Split polling error:', error);
                clearInterval(window.splitPollingIntervalId);
                isProcessingJob = false;
                hideStatus();
                if (statusText) statusText.textContent = `Polling failed: ${error.message}`;
                if (statusPanel) statusPanel.classList.remove('hidden');
            }
        }, 5000);
    }

    // --- 7. CHECK FOR ACTIVE JOBS ON PAGE LOAD ---

    async function checkForActiveJobs() {
        try {
            const response = await fetch(`${API_BASE_URL}/history`);
            if (!response.ok) return;

            const history = await response.json();
            const activeJob = history.find(job => job.status === 'In Progress');

            if (activeJob) {
                console.log("Found active job on page load:", activeJob);
                showStatus(`Resuming job: ${activeJob.job_display_name}...`);

                if (activeJob.job_type === 'split') {
                    pollSplitJobStatus(activeJob.id);
                } else {
                    pollJobStatus(activeJob.id, {
                        isClearJob: (activeJob.job_display_name.includes('Clear'))
                    });
                }
            }
        } catch (error) {
            console.error('Error checking for active jobs:', error);
        }
    }

    // --- 8. INITIALIZE ---

    if (vjBackground) {
        vjBackground.playbackRate = 1.0;
        vjBackground.pause();
    }

    updateControls();
    checkForActiveJobs();

});

// Tooltip toggle for tagging info
document.addEventListener('DOMContentLoaded', () => {
    const infoBtn = document.getElementById('tagging-info-btn');
    const tooltip = document.getElementById('tagging-tooltip');

    if (infoBtn && tooltip) {
        infoBtn.addEventListener('click', (e) => {
            e.preventDefault();
            tooltip.classList.toggle('hidden');
        });

        // Close when clicking outside
        document.addEventListener('click', (e) => {
            if (!infoBtn.contains(e.target) && !tooltip.contains(e.target)) {
                tooltip.classList.add('hidden');
            }
        });
    }
});

// Mode button hover tooltips
document.addEventListener('DOMContentLoaded', () => {
    const modeButtons = document.querySelectorAll('.mode-button');

    modeButtons.forEach(button => {
        const tooltip = button.parentElement.querySelector('.mode-tooltip');

        if (tooltip) {
            button.addEventListener('mouseenter', () => {
                tooltip.classList.remove('hidden');
            });

            button.addEventListener('mouseleave', () => {
                tooltip.classList.add('hidden');
            });
        }
    });
});