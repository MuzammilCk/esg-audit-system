
function switchTab(tabId) {
    // Buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    // Find button that called this, but since we pass ID, we assume logic based on text or structure.
    // Simplification: query by onclick attribute or reset all manual.
    // Let's just rely on simple class toggling.
    const buttons = document.querySelectorAll('.tab-btn');
    if(tabId === 'provenance') buttons[0].classList.add('active');
    if(tabId === 'privacy') buttons[1].classList.add('active');

    // Sections
    document.querySelectorAll('.module-section').forEach(sec => {
        sec.classList.remove('active');
    });
    document.getElementById(tabId).classList.add('active');
}

// Drag and Drop Logic
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
        handleFile(fileInput.files[0]);
    }
});

async function handleFile(file) {
    const resultDiv = document.getElementById('c2pa-result');
    resultDiv.innerHTML = '<div class="blink">SCANNING_FILE_STRUCTURE...</div>';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/verify', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        displayC2PAResult(data);
    } catch (error) {
        resultDiv.innerHTML = `<span style="color:red">ERROR: CONNECTION_FAILURE</span>`;
    }
}

function displayC2PAResult(data) {
    const resultDiv = document.getElementById('c2pa-result');
    const color = data.status === 'VERIFIED' ? '#0f0' : (data.status === 'SYNTHETIC_AI' ? '#f0f' : '#f00');
    
    let html = `<div style="color:${color}; font-weight:bold; font-size:1.2rem; margin-bottom:10px;">STATUS: ${data.status}</div>`;
    html += `<div>TRUST_SCORE: ${(data.trust_score * 100).toFixed(1)}%</div>`;
    html += `<div>ISSUER: ${data.issuer || 'UNKNOWN'}</div>`;
    html += `<div>SOFTWARE: ${data.software_agent || 'UNKNOWN'}</div>`;
    
    if (data.assertions && data.assertions.length > 0) {
        html += `<div style="margin-top:10px; border-top:1px dashed #555; paddingTop:5px;">ASSERTIONS_DETECTED:</div>`;
        data.assertions.forEach(a => {
            html += `<div style="padding-left:10px; font-size:0.9rem;">> ${a.label}</div>`;
        });
    }

    resultDiv.innerHTML = html;
}

// PII Logic
async function processPII() {
    const text = document.getElementById('pii-input').value;
    const resultDiv = document.getElementById('pii-result');
    
    if (!text) return;
    
    resultDiv.innerHTML = '<div class="blink">ENCODING_STREAM...</div>';

    try {
        const response = await fetch('/api/redact', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: text})
        });
        const data = await response.json();
        
        displayPIIResult(data);
    } catch (error) {
        resultDiv.innerHTML = `<span style="color:red">ERROR: MASKING_FAILURE</span>`;
    }
}

function displayPIIResult(data) {
    const resultDiv = document.getElementById('pii-result');
    let html = `<div>// OUTPUT_STREAM</div>`;
    html += `<div style="color:#0f0; margin-top:10px;">${data.masked_text}</div>`;
    html += `<div style="margin-top:15px; border-top:1px dashed #555; padding-top:10px; color:#aaa;">// REDIS_KEY: <span style="color:#fff">${data.key}</span></div>`;
    resultDiv.innerHTML = html;
}
