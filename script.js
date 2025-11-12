// --- Wait for the DOM to be ready ---
document.addEventListener('DOMContentLoaded', () => {

    // --- 1. GLOBAL STATE & CONFIG ---
    let uploadedFile = null; // Holds the currently selected file object
    let taggedSplitFiles = []; // Tracks tagged files in the playlist
    let isProcessingJob = false; // Prevents multiple simultaneous jobs
    const API_BASE_URL = 'http://127.0.0.1:5001';

    // Config object from your backend (app_1.py)
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
    const statusPanel = document.getElementById('status-panel');
    const statusText = document.getElementById('status-text');
    const vjBackground = document.getElementById('vj-background');

    // UI Areas
    const mainUploadArea = document.getElementById('main-upload-area');
    const splitWorkspaceArea = document.getElementById('split-workspace-area');
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

    // Split Workspace Controls
    const startOverBtn = document.getElementById('start-over-btn');
    const splitResultsList = document.getElementById('split-results-list');

    // Main Results
    const mainResultsTitle = document.getElementById('main-results-title');
    const mainTagResultContainer = document.getElementById('main-tag-result-container');

    // --- 3. HELPER FUNCTIONS ---

    /**
     * Controls VJ background video playback speed and state
     */
    function setVideoProcessing(isProcessing) {
        if (isProcessing) {
            vjBackground.playbackRate = 0.5; // Slow down to 50% speed
            vjBackground.play();
            vjBackground.classList.remove('paused');
        } else {
            vjBackground.pause();
            vjBackground.classList.add('paused');
        }
    }

    /**
     * Logs actions to the backend for tracking
     */
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

    /**
     * Resets the entire UI to its default "upload" state
     */
    function resetUiToDefault() {
        mainUploadArea.classList.remove('hidden');
        splitWorkspaceArea.classList.add('hidden');
        mainResultsArea.classList.add('hidden');
        statusPanel.classList.add('hidden');

        dragArea.innerHTML = `<p class="text-sm text-blue-600">Drag & drop your XML file here</p><p class="text-xs text-gray-500 mt-1">or click to browse</p>`;
        dragArea.style.borderStyle = 'dashed';

        uploadedFile = null;
        startJobBtn.disabled = true;

        document.getElementById('mode-tag').checked = true;
        document.getElementById('level-recommended').checked = true;
        updateControls();

        sessionStorage.clear();
        taggedSplitFiles = [];
    }

    /**
     * Updates the UI to show the selected file name
     */
    function setDragAreaToFileSelected(fileName) {
        dragArea.innerHTML = `<p class="text-lg font-medium text-gray-700">File Selected:</p><p class="text-sm text-gray-500">${fileName}</p>`;
        dragArea.style.borderStyle = 'solid';
        startJobBtn.disabled = false;
    }

    /**
     * The main function for handling a newly selected file
     */
    function handleFile(file) {
        if (!file || !file.name.endsWith('.xml')) {
            alert("Only .xml files are allowed.");
            return;
        }

        uploadedFile = file;
        setDragAreaToFileSelected(uploadedFile.name);
        mainResultsArea.classList.add('hidden');
        statusPanel.classList.add('hidden');
        sessionStorage.removeItem('lastSplitResults');
        sessionStorage.removeItem('taggedSplitFiles');
        taggedSplitFiles = [];
        logAction(`User selected file: ${uploadedFile.name}`);
    }

    /**
     * Shows the correct tag preview based on the selected radio button
     */
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

    /**
     * Updates the UI based on the selected mode (Tag, Split, Clear)
     */
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

    /**
     * Shows status panel with processing message
     */
    function showStatus(message) {
        statusText.textContent = message;
        statusPanel.classList.remove('hidden');
        mainResultsArea.classList.add('hidden');
        mainControls.style.pointerEvents = 'none';
        mainControls.style.opacity = '0.5';
        startJobBtn.disabled = true;
        setVideoProcessing(true); // Start video animation
    }

    /**
     * Hides status panel and re-enables controls
     */
    function hideStatus() {
        statusPanel.classList.add('hidden');
        mainControls.style.pointerEvents = 'auto';
        mainControls.style.opacity = '1';
        startJobBtn.disabled = (uploadedFile === null);
        setVideoProcessing(false); // Stop video animation
    }

    /**
     * Displays the split workspace with file list
     */
    function displaySplitWorkspace(files) {
        mainUploadArea.classList.add('hidden');
        statusPanel.classList.add('hidden');
        mainResultsArea.classList.add('hidden');
        splitWorkspaceArea.classList.remove('hidden');

        splitResultsList.innerHTML = '';
        if (!files || files.length === 0) {
            splitResultsList.innerHTML = '<li class="text-gray-500">No split files generated or found.</li>';
            return;
        }

        files.forEach(filePath => {
            const li = document.createElement('li');
            li.className = 'flex justify-between items-center p-3 bg-white border border-gray-200 rounded-lg shadow-sm';
            li.dataset.filepath = filePath;
            const justFileName = filePath.split('/').pop();

            const fileNameSpan = document.createElement('span');
            fileNameSpan.className = 'font-mono text-sm text-gray-700';
            fileNameSpan.textContent = justFileName;

            const buttonGroup = document.createElement('div');
            buttonGroup.className = 'space-x-2';

            const isTagged = taggedSplitFiles.includes(justFileName);

            const downloadOriginalBtn = document.createElement('a');
            downloadOriginalBtn.href = `${API_BASE_URL}/download_split_file?path=${encodeURIComponent(filePath)}`;
            downloadOriginalBtn.textContent = 'Download Original';
            downloadOriginalBtn.dataset.action = 'download-original';
            downloadOriginalBtn.className = 'px-3 py-1 bg-gray-200 text-gray-800 text-xs font-semibold rounded-full hover:bg-gray-300';
            downloadOriginalBtn.setAttribute('download', '');

            const tagBtn = document.createElement('button');
            tagBtn.textContent = 'Tag this File';
            tagBtn.dataset.action = 'tag';
            tagBtn.className = 'px-3 py-1 bg-blue-500 text-white text-xs font-semibold rounded-full hover:bg-blue-600';

            const taggingSpinnerBtn = document.createElement('button');
            taggingSpinnerBtn.textContent = 'Tagging...';
            taggingSpinnerBtn.dataset.action = 'tagging';
            taggingSpinnerBtn.className = 'px-3 py-1 bg-blue-300 text-white text-xs font-semibold rounded-full animate-pulse cursor-not-allowed hidden';

            const downloadTaggedBtn = document.createElement('a');
            downloadTaggedBtn.href = `${API_BASE_URL}/export_xml`;
            downloadTaggedBtn.textContent = 'Download Tagged';
            downloadTaggedBtn.dataset.action = 'download-tagged';
            downloadTaggedBtn.className = 'px-3 py-1 bg-green-500 text-white text-xs font-semibold rounded-full hover:bg-green-600';
            downloadTaggedBtn.setAttribute('download', '');

            buttonGroup.appendChild(downloadOriginalBtn);
            buttonGroup.appendChild(tagBtn);
            buttonGroup.appendChild(taggingSpinnerBtn);
            buttonGroup.appendChild(downloadTaggedBtn);

            if (isTagged) {
                tagBtn.classList.add('hidden');
                taggingSpinnerBtn.classList.add('hidden');
                downloadTaggedBtn.classList.remove('hidden');
            } else {
                tagBtn.classList.remove('hidden');
                taggingSpinnerBtn.classList.add('hidden');
                downloadTaggedBtn.classList.add('hidden');
            }

            li.appendChild(fileNameSpan);
            li.appendChild(buttonGroup);
            splitResultsList.appendChild(li);
        });
    }

    /**
     * Handles the success UI for a "Tag Library" or "Clear Tags" job
     */
    function displayMainTagResult(jobDisplayName, isClearJob = false) {
        mainResultsTitle.textContent = isClearJob ? 'Clear Complete!' : 'Tagging Complete!';
        mainTagResultContainer.innerHTML = '';

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

    /**
     * Calls the backend to tag a single split file
     */
    async function startTaggingSpecificFile(filePath, tagButton) {
        const fileName = filePath.split('/').pop();
        logAction(`User clicked 'Tag this File' for: ${fileName}`);

        const parentButtonGroup = tagButton.parentElement;
        parentButtonGroup.querySelector('[data-action="tag"]').classList.add('hidden');
        parentButtonGroup.querySelector('[data-action="download-original"]').classList.add('hidden');
        parentButtonGroup.querySelector('[data-action="tagging"]').classList.remove('hidden');

        const selectedLevelValue = document.querySelector('input[name="split-tag-level"]:checked').value;
        const config = { ...tagConfigurations[selectedLevelValue] };

        try {
            const response = await fetch(`${API_BASE_URL}/tag_split_file`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath, config: config }),
            });
            const result = await response.json();

            if (response.status === 202 && result.job_id) {
                pollJobStatus(result.job_id, {
                    isSplitChildJob: true,
                    fileName: fileName
                });
                if (!taggedSplitFiles.includes(fileName)) {
                    taggedSplitFiles.push(fileName);
                }
                sessionStorage.setItem('taggedSplitFiles', JSON.stringify(taggedSplitFiles));
                logAction(`Tagging job for split file started with ID ${result.job_id}`);
            } else {
                throw new Error(result.error || `Failed to start tagging job`);
            }
        } catch (error) {
            console.error('Failed to start tagging job:', error);
            parentButtonGroup.querySelector('[data-action="tag"]').classList.remove('hidden');
            parentButtonGroup.querySelector('[data-action="download-original"]').classList.remove('hidden');
            parentButtonGroup.querySelector('[data-action="tagging"]').classList.add('hidden');
        }
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
    startOverBtn.addEventListener('click', resetUiToDefault);

    splitResultsList.addEventListener('click', (e) => {
        const button = e.target.closest('button, a');
        if (!button) return;
        const listItem = e.target.closest('li');
        if (!listItem || !listItem.dataset.filepath) return;

        const filePath = listItem.dataset.filepath;
        const action = button.dataset.action;
        const justFileName = filePath.split('/').pop();

        if (action === 'tag') {
            e.preventDefault();
            startTaggingSpecificFile(filePath, button);
        } else if (action === 'download-original') {
            logAction(`User downloaded original split file: ${justFileName}`);
        } else if (action === 'download-tagged') {
            logAction(`User downloaded tagged split file: ${justFileName}`);
        }
    });

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
            statusText.textContent = `Upload failed: ${error.message}. Is the server running?`;
            statusPanel.classList.remove('hidden');
            logAction(`Job failed to start: ${error.message}`);
        }
    });

    // --- 6. POLLING FUNCTIONS ---

    /**
     * Polls for tagging/clear job status with timeout protection
     */
    function pollJobStatus(jobIdToTrack, options = {}) {
        const { isSplitChildJob = false, fileName = '', isClearJob = false } = options;
        let pollAttempts = 0;
        const MAX_POLLS = 120; // 10 minutes at 5s intervals

        if (window.pollingIntervalId) clearInterval(window.pollingIntervalId);

        window.pollingIntervalId = setInterval(async () => {
            if (pollAttempts++ > MAX_POLLS) {
                clearInterval(window.pollingIntervalId);
                isProcessingJob = false;
                hideStatus();
                statusText.textContent = "Job timed out after 10 minutes. Please check server.";
                statusPanel.classList.remove('hidden');
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

                    if (!isSplitChildJob) {
                        showStatus(`Processing ${jobName}... (Status: ${currentJob.status})`);
                    }

                    if (currentJob.status === 'Completed' || currentJob.status === 'Failed') {
                        clearInterval(window.pollingIntervalId);
                        isProcessingJob = false;

                        if (currentJob.status === 'Completed') {
                            logAction(`Job completed for ${jobName}`);

                            if (isSplitChildJob) {
                                const lastSplitResults = sessionStorage.getItem('lastSplitResults');
                                if (lastSplitResults) {
                                    displaySplitWorkspace(JSON.parse(lastSplitResults));
                                }
                            } else {
                                hideStatus();
                                displayMainTagResult(jobName, isClearJob);
                                setDragAreaToFileSelected(uploadedFile.name);
                                sessionStorage.removeItem('lastSplitResults');
                            }
                        } else {
                            logAction(`Job failed for ${jobName}`);
                            if (isSplitChildJob) {
                                const lastSplitResults = sessionStorage.getItem('lastSplitResults');
                                if (lastSplitResults) {
                                    displaySplitWorkspace(JSON.parse(lastSplitResults));
                                }
                            } else {
                                hideStatus();
                                statusText.textContent = `Job '${jobName}' failed. Check logs.`;
                                statusPanel.classList.remove('hidden');
                            }
                        }
                    }
                }
            } catch (error) {
                console.error('Polling error:', error);
                clearInterval(window.pollingIntervalId);
                isProcessingJob = false;
                if (!isSplitChildJob) {
                    hideStatus();
                    statusText.textContent = `Polling failed: ${error.message}`;
                    statusPanel.classList.remove('hidden');
                }
            }
        }, 5000);
    }

    /**
     * Polls for split job status with timeout protection
     */
    function pollSplitJobStatus(jobIdToTrack) {
        let pollAttempts = 0;
        const MAX_POLLS = 120; // 10 minutes at 5s intervals

        if (window.splitPollingIntervalId) clearInterval(window.splitPollingIntervalId);

        window.splitPollingIntervalId = setInterval(async () => {
            if (pollAttempts++ > MAX_POLLS) {
                clearInterval(window.splitPollingIntervalId);
                isProcessingJob = false;
                hideStatus();
                statusText.textContent = "Split job timed out after 10 minutes. Please check server.";
                statusPanel.classList.remove('hidden');
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
                            const files = JSON.parse(currentJob.result_data);
                            displaySplitWorkspace(files);

                            sessionStorage.setItem('lastSplitResults', currentJob.result_data);
                            taggedSplitFiles = [];
                            sessionStorage.setItem('taggedSplitFiles', JSON.stringify([]));

                            logAction(`Split job ${jobIdToTrack} completed successfully.`);
                        } else {
                            hideStatus();
                            statusText.textContent = `Job '${currentJob.job_display_name}' failed. Check logs.`;
                            statusPanel.classList.remove('hidden');
                            logAction(`Split job ${jobIdToTrack} failed.`);
                        }
                    }
                }
            } catch (error) {
                console.error('Split polling error:', error);
                clearInterval(window.splitPollingIntervalId);
                isProcessingJob = false;
                hideStatus();
                statusText.textContent = `Polling failed: ${error.message}`;
                statusPanel.classList.remove('hidden');
            }
        }, 5000);
    }

    // --- 7. RESTORE PREVIOUS STATE ---

    /**
     * Restores split workspace from sessionStorage if available
     */
    function restorePreviousState() {
        const lastSplitResults = sessionStorage.getItem('lastSplitResults');
        if (lastSplitResults) {
            console.log("Found previous split results. Restoring workspace.");
            const taggedFilesFromStorage = sessionStorage.getItem('taggedSplitFiles');
            if (taggedFilesFromStorage) {
                taggedSplitFiles = JSON.parse(taggedFilesFromStorage);
            }
            try {
                const files = JSON.parse(lastSplitResults);
                displaySplitWorkspace(files);
            } catch (e) {
                console.error("Could not parse split results from sessionStorage. Starting fresh.", e);
                statusText.textContent = "Previous session data was corrupted. Starting fresh.";
                sessionStorage.clear();
                resetUiToDefault();
            }
        } else {
            resetUiToDefault();
        }
    }

    // --- 8. INITIALIZE ---

    // Set up video on load
    if (vjBackground) {
        vjBackground.playbackRate = 0.25; // Pre-set slow speed
        vjBackground.pause(); // Ensure paused on load
    }

    restorePreviousState();

}); // End of DOMContentLoaded