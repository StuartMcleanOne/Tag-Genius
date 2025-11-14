document.addEventListener('DOMContentLoaded', () => {
    const API_BASE_URL = 'http://127.0.0.1:5001';
    const workspaceFilesList = document.getElementById('workspace-files-list');
    const loadingMessage = document.getElementById('loading-message');
    const emptyMessage = document.getElementById('empty-message');

    let taggedSplitFiles = [];

    const tagConfigurations = {
        "2": { "level": "Essential", "sub_genre": 1, "energy_vibe": 1, "situation_environment": 1, "components": 1, "time_period": 1 },
        "3": { "level": "Recommended", "sub_genre": 2, "energy_vibe": 2, "situation_environment": 2, "components": 2, "time_period": 1 },
        "4": { "level": "Detailed", "sub_genre": 3, "energy_vibe": 3, "situation_environment": 3, "components": 3, "time_period": 1 }
    };

    // Load tagged files from sessionStorage
    function loadTaggedFiles() {
        const stored = sessionStorage.getItem('taggedSplitFiles');
        if (stored) {
            try {
                taggedSplitFiles = JSON.parse(stored);
            } catch (e) {
                taggedSplitFiles = [];
            }
        }
    }

    // Save tagged files to sessionStorage
    function saveTaggedFiles() {
        sessionStorage.setItem('taggedSplitFiles', JSON.stringify(taggedSplitFiles));
    }

    // Display files in workspace
    function displayFiles(files) {
        loadingMessage.classList.add('hidden');

        if (!files || files.length === 0) {
            emptyMessage.classList.remove('hidden');
            return;
        }

        workspaceFilesList.classList.remove('hidden');
        workspaceFilesList.innerHTML = '';

        files.forEach(filePath => {
            const li = document.createElement('li');
            li.className = 'flex justify-between items-center p-4 bg-white bg-opacity-5 backdrop-blur-lg rounded-lg border border-white border-opacity-10';
            li.dataset.filepath = filePath;
            const justFileName = filePath.split('/').pop();

            const fileNameSpan = document.createElement('span');
            fileNameSpan.className = 'font-mono text-base text-white font-semibold';
            fileNameSpan.textContent = justFileName;

            const buttonGroup = document.createElement('div');
            buttonGroup.className = 'flex gap-2';

            const isTagged = taggedSplitFiles.includes(justFileName);

            // Download Original Button
            const downloadOriginalBtn = document.createElement('a');
            downloadOriginalBtn.href = `${API_BASE_URL}/download_split_file?path=${encodeURIComponent(filePath)}`;
            downloadOriginalBtn.textContent = 'Download Original';
            downloadOriginalBtn.dataset.action = 'download-original';
            downloadOriginalBtn.className = 'px-4 py-2 bg-gray-200 text-gray-800 text-sm font-semibold rounded-lg hover:bg-gray-300 transition-colors';
            downloadOriginalBtn.setAttribute('download', '');

            // Tag Button
            const tagBtn = document.createElement('button');
            tagBtn.textContent = 'Tag this File';
            tagBtn.dataset.action = 'tag';
            tagBtn.className = 'px-4 py-2 bg-blue-500 text-white text-sm font-semibold rounded-lg hover:bg-blue-600 transition-colors';

            // Tagging Spinner Button
            const taggingSpinnerBtn = document.createElement('button');
            taggingSpinnerBtn.textContent = 'Tagging...';
            taggingSpinnerBtn.dataset.action = 'tagging';
            taggingSpinnerBtn.className = 'px-4 py-2 bg-blue-300 text-white text-sm font-semibold rounded-lg animate-pulse cursor-not-allowed hidden';

            // Download Tagged Button
            const downloadTaggedBtn = document.createElement('a');
            downloadTaggedBtn.href = `${API_BASE_URL}/export_xml`;
            downloadTaggedBtn.textContent = 'Download Tagged';
            downloadTaggedBtn.dataset.action = 'download-tagged';
            downloadTaggedBtn.className = 'px-4 py-2 bg-green-500 text-white text-sm font-semibold rounded-lg hover:bg-green-600 transition-colors';
            downloadTaggedBtn.setAttribute('download', '');

            buttonGroup.appendChild(downloadOriginalBtn);
            buttonGroup.appendChild(tagBtn);
            buttonGroup.appendChild(taggingSpinnerBtn);
            buttonGroup.appendChild(downloadTaggedBtn);

            // Show/hide buttons based on tagged status
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
            workspaceFilesList.appendChild(li);
        });
    }

    // Start tagging a file
    async function startTaggingFile(filePath, tagButton) {
        const fileName = filePath.split('/').pop();

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
                pollJobStatus(result.job_id, fileName);

                if (!taggedSplitFiles.includes(fileName)) {
                    taggedSplitFiles.push(fileName);
                    saveTaggedFiles();
                }
            } else {
                throw new Error(result.error || 'Failed to start tagging job');
            }
        } catch (error) {
            console.error('Failed to start tagging job:', error);
            parentButtonGroup.querySelector('[data-action="tag"]').classList.remove('hidden');
            parentButtonGroup.querySelector('[data-action="download-original"]').classList.remove('hidden');
            parentButtonGroup.querySelector('[data-action="tagging"]').classList.add('hidden');
        }
    }

    // Poll job status
    function pollJobStatus(jobId, fileName) {
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/history`);
                if (!response.ok) throw new Error('Failed to fetch history');

                const history = await response.json();
                const job = history.find(j => j.id === jobId);

                if (job && (job.status === 'Completed' || job.status === 'Failed')) {
                    clearInterval(pollInterval);

                    if (job.status === 'Completed') {
                        // Reload the workspace to show updated button states
                        const lastSplitResults = sessionStorage.getItem('lastSplitResults');
                        if (lastSplitResults) {
                            displayFiles(JSON.parse(lastSplitResults));
                        }
                    } else {
                        alert(`Tagging failed for ${fileName}`);
                        // Reload to reset button states
                        const lastSplitResults = sessionStorage.getItem('lastSplitResults');
                        if (lastSplitResults) {
                            displayFiles(JSON.parse(lastSplitResults));
                        }
                    }
                }
            } catch (error) {
                console.error('Polling error:', error);
                clearInterval(pollInterval);
            }
        }, 5000);
    }

    // Handle button clicks
    workspaceFilesList.addEventListener('click', (e) => {
        const button = e.target.closest('button, a');
        if (!button) return;

        const listItem = e.target.closest('li');
        if (!listItem || !listItem.dataset.filepath) return;

        const filePath = listItem.dataset.filepath;
        const action = button.dataset.action;

        if (action === 'tag') {
            e.preventDefault();
            startTaggingFile(filePath, button);
        }
    });

    // Load workspace on page load
    loadTaggedFiles();

    // Check if we're restoring from a specific job (from history page)
    const restoreJobId = sessionStorage.getItem('restoreJobId');
    if (restoreJobId) {
        sessionStorage.removeItem('restoreJobId');
        restoreJobFromHistory(restoreJobId);
    } else {
        // Normal load from sessionStorage
        const lastSplitResults = sessionStorage.getItem('lastSplitResults');
        if (lastSplitResults) {
            try {
                const files = JSON.parse(lastSplitResults);
                displayFiles(files);
            } catch (e) {
                console.error('Could not parse split results:', e);
                loadingMessage.classList.add('hidden');
                emptyMessage.classList.remove('hidden');
            }
        } else {
            loadingMessage.classList.add('hidden');
            emptyMessage.classList.remove('hidden');
        }
    }

    // Restore job from history database
    async function restoreJobFromHistory(jobId) {
        try {
            const response = await fetch(`${API_BASE_URL}/history`);
            if (!response.ok) throw new Error('Failed to fetch history');

            const history = await response.json();
            const job = history.find(j => j.id == jobId);

            if (!job) {
                console.error('Job not found:', jobId);
                loadingMessage.classList.add('hidden');
                emptyMessage.classList.remove('hidden');
                return;
            }

            if (job.job_type === 'split' && job.status === 'Completed' && job.result_data) {
                const files = JSON.parse(job.result_data);
                sessionStorage.setItem('lastSplitResults', job.result_data);
                displayFiles(files);
            } else {
                console.error('Job is not a completed split job:', job);
                loadingMessage.classList.add('hidden');
                emptyMessage.classList.remove('hidden');
            }
        } catch (error) {
            console.error('Error restoring job from history:', error);
            loadingMessage.classList.add('hidden');
            emptyMessage.classList.remove('hidden');
        }
    }
});