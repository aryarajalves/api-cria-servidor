// State
let credentials = {
    host: '',
    username: '',
    password: ''
};

let isConnected = false;

// DOM Elements
const views = {
    dashboard: document.getElementById('dashboard-view'),
    logs: document.getElementById('logs-view'),
    settings: document.getElementById('settings-view') // Not implemented yet
};

const navItems = document.querySelectorAll('.nav-item');
const connectionForm = document.getElementById('connectionForm');
const connectionCard = document.getElementById('connectionCard');
const servicesGrid = document.getElementById('servicesGrid');
const serverInfoDisplay = document.getElementById('serverInfoDisplay');
const connectedHost = document.getElementById('connectedHost');
const statusText = document.getElementById('statusText');
const statusIndicator = document.querySelector('.status-indicator');
const logsContent = document.getElementById('logsContent');

// Event Listeners
navItems.forEach(item => {
    item.addEventListener('click', () => {
        const tab = item.dataset.tab;
        switchTab(tab);
    });
});

connectionForm.addEventListener('submit', (e) => {
    e.preventDefault();
    connect();
});

// Functions
function switchTab(tabName) {
    // Update Nav
    navItems.forEach(item => {
        if (item.dataset.tab === tabName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Update View
    Object.keys(views).forEach(key => {
        if (views[key]) {
            if (key === tabName) {
                views[key].classList.add('active');
            } else {
                views[key].classList.remove('active');
            }
        }
    });
}

async function connect() {
    const host = document.getElementById('host').value;
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    if (!host || !username || !password) {
        showToast('Por favor, preencha todos os campos.', 'error');
        return;
    }

    const btn = connectionForm.querySelector('button');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Conectando...';
    btn.disabled = true;

    try {
        const response = await fetch('/verify-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ host, username, password })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Falha na conexão');
        }

        // Se chegou aqui, conectou com sucesso
        credentials = { host, username, password };
        isConnected = true;

        updateConnectionUI();
        showToast(result.message, 'success');
        log(`Conectado ao servidor ${host} como ${username}`, 'success');

        if (result.detected_stacks && result.detected_stacks.length > 0) {
            log(`Stacks já ativas: ${result.detected_stacks.join(', ')}`, 'info');
            updateStacksStatus(result.detected_stacks);
        }

        if (result.system_status) {
            updateSystemStatus(result.system_status);
        }

    } catch (error) {
        showToast(error.message, 'error');
        log(`Erro de conexão: ${error.message}`, 'error');
        isConnected = false;
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

let systemState = {
    docker: false,
    swarm: false,
    network: false
};

function updateSystemStatus(status) {
    systemState = status;

    // Docker
    const btnDocker = document.getElementById('btn-install-docker');
    if (status.docker) {
        btnDocker.textContent = 'Instalado';
        btnDocker.classList.add('secondary');
        btnDocker.disabled = true;
        log(`Docker detectado: Versão ${status.docker}`, 'success');
    }

    // Swarm
    const btnSwarm = document.getElementById('btn-init-swarm');
    if (status.swarm) {
        btnSwarm.textContent = 'Ativo';
        btnSwarm.classList.add('secondary');
        btnSwarm.disabled = true;
        log('Docker Swarm já está ativo.', 'success');
    }

    // Network
    const btnNetwork = document.getElementById('btn-create-network');
    if (status.network) {
        btnNetwork.textContent = 'Criada';
        btnNetwork.classList.add('secondary');
        btnNetwork.disabled = true;
        log("Rede 'network_swarm_public' já existe.", 'success');
    }

    updateServiceButtons();
}

function updateServiceButtons() {
    const dependenciesMet = systemState.docker && systemState.swarm && systemState.network;
    const serviceButtons = [
        'btn-install-traefik', 'btn-install-portainer', 'btn-install-redis',
        'btn-install-postgres', 'btn-install-n8n', 'btn-install-chatwoot',
        'btn-install-rabbitmq', 'btn-install-minio', 'btn-install-baserow'
    ];

    serviceButtons.forEach(btnId => {
        const btn = document.getElementById(btnId);
        if (btn) {
            // Only modify if it's not already installed (checked by class 'secondary')
            if (!btn.classList.contains('secondary')) {
                let isEnabled = dependenciesMet;
                let title = "";

                // Specific logic for Chatwoot
                if (btnId === 'btn-install-chatwoot') {
                    const chatwootDeps = installedServices.has('redis') &&
                        installedServices.has('postgres') &&
                        installedServices.has('minio');

                    if (dependenciesMet && !chatwootDeps) {
                        isEnabled = false;
                        title = "Requer Redis, Postgres e Minio instalados";
                    } else if (!dependenciesMet) {
                        title = "Requer Docker, Swarm e Rede Overlay";
                    }
                }
                // Specific logic for N8N
                else if (btnId === 'btn-install-n8n') {
                    const n8nDeps = installedServices.has('redis') &&
                        installedServices.has('postgres');

                    if (dependenciesMet && !n8nDeps) {
                        isEnabled = false;
                        title = "Requer Redis e Postgres instalados";
                    } else if (!dependenciesMet) {
                        title = "Requer Docker, Swarm e Rede Overlay";
                    }
                }
                // Specific logic for Baserow
                else if (btnId === 'btn-install-baserow') {
                    const baserowDeps = installedServices.has('redis') &&
                        installedServices.has('postgres');

                    if (dependenciesMet && !baserowDeps) {
                        isEnabled = false;
                        title = "Requer Redis e Postgres instalados";
                    } else if (!dependenciesMet) {
                        title = "Requer Docker, Swarm e Rede Overlay";
                    }
                }
                else {
                    if (!dependenciesMet) {
                        title = "Requer Docker, Swarm e Rede Overlay";
                    }
                }

                btn.disabled = !isEnabled;
                btn.title = title;

                if (!isEnabled) {
                    btn.style.opacity = '0.5';
                    btn.style.cursor = 'not-allowed';
                } else {
                    btn.style.opacity = '1';
                    btn.style.cursor = 'pointer';
                }
            }
        }
    });
}

// --- Logic for Stacks Status and Env Vars ---

// --- Logic for Stacks Status and Env Vars ---

let installedServices = new Set();

function updateStacksStatus(activeStacks) {
    // Map of stack_name -> { installBtnId, updateBtnId }
    // Note: stack names usually match the service name prefix or the stack name used in deploy
    // In installer.py we use names like: traefik, portainer, redis, postgres, n8n, chatwoot, rabbitmq, minio, baserow

    const stackMap = {
        'traefik': 'traefik',
        'portainer': 'portainer',
        'redis': 'redis',
        'postgres': 'postgres',
        'n8n': 'n8n',
        'chatwoot': 'chatwoot',
        'rabbitmq': 'rabbitmq',
        'minio': 'minio',
        'baserow': 'baserow'
    };

    activeStacks.forEach(stackName => {
        // The stackName from backend might be "traefik", "portainer", etc.
        // Check if we have a mapping
        const key = Object.keys(stackMap).find(k => stackName.includes(k));

        if (key) {
            installedServices.add(key); // Track installed service

            const installBtn = document.getElementById(`btn-install-${key}`);
            const updateBtn = document.getElementById(`btn-update-${key}`);

            if (installBtn) {
                installBtn.textContent = 'Instalado';
                installBtn.classList.add('secondary');
                installBtn.disabled = true;
            }

            if (updateBtn && key !== 'redis') {
                updateBtn.style.display = 'inline-block';
            }
        }
    });

    updateServiceButtons(); // Re-evaluate buttons based on new installed services
}

// Modal Functions
let currentStackForEnv = '';

async function openEnvModal(stackName) {
    currentStackForEnv = stackName;
    document.getElementById('modalStackName').textContent = stackName;
    document.getElementById('envModal').style.display = 'block';
    const container = document.getElementById('envVarsContainer');
    container.innerHTML = '<p>Carregando...</p>';

    try {
        const response = await callApi(`/get-stack-env/${stackName}`);
        let envVars = response.env_vars;

        container.innerHTML = '';

        // Filter variables based on stack
        if (stackName.includes('traefik')) {
            const filtered = {};
            for (const [k, v] of Object.entries(envVars)) {
                if (k.includes('TRAEFIK_CERTIFICATESRESOLVERS_LETSENCRYPTRESOLVER_ACME_EMAIL')) {
                    filtered[k] = v;
                }
            }
            envVars = filtered;
        } else if (stackName.includes('postgres')) {
            const filtered = {};
            for (const [k, v] of Object.entries(envVars)) {
                if (k.includes('POSTGRES_PASSWORD')) {
                    filtered[k] = v;
                }
            }
            envVars = filtered;
        }

        if (Object.keys(envVars).length === 0) {
            container.innerHTML = '<p>Nenhuma variável editável encontrada.</p>';
        }

        for (const [key, value] of Object.entries(envVars)) {
            addEnvVarField(key, value);
        }
    } catch (error) {
        container.innerHTML = `<p class="error">Erro ao carregar variáveis: ${error.message}</p>`;
    }
}

function closeEnvModal() {
    document.getElementById('envModal').style.display = 'none';
    currentStackForEnv = '';
}

function addEnvVarField(key = '', value = '') {
    const container = document.getElementById('envVarsContainer');
    const div = document.createElement('div');
    div.className = 'env-var-row';
    div.innerHTML = `
        <input type="text" placeholder="Nome da Variável" value="${key}" class="env-key">
        <input type="text" placeholder="Valor" value="${value}" class="env-value">
        <button class="btn-small danger" onclick="this.parentElement.remove()">X</button>
    `;
    container.appendChild(div);
}

async function saveEnvVars() {
    if (!currentStackForEnv) return;

    const container = document.getElementById('envVarsContainer');
    const rows = container.querySelectorAll('.env-var-row');
    const envVars = {};

    rows.forEach(row => {
        const key = row.querySelector('.env-key').value.trim();
        const value = row.querySelector('.env-value').value.trim();
        if (key) {
            envVars[key] = value;
        }
    });

    try {
        await callApi('/update-stack-env', {
            stack_name: currentStackForEnv,
            env_vars: envVars
        });
        showToast('Variáveis atualizadas com sucesso!', 'success');
        closeEnvModal();
    } catch (error) {
        showToast(`Erro ao atualizar: ${error.message}`, 'error');
    }
}

// Close modal if clicked outside
window.onclick = function (event) {
    const modal = document.getElementById('envModal');
    if (event.target == modal) {
        closeEnvModal();
    }
}

function updateConnectionUI() {
    if (isConnected) {
        connectionCard.style.display = 'none';
        servicesGrid.style.display = 'grid';
        serverInfoDisplay.style.display = 'flex';
        connectedHost.textContent = credentials.host;
        statusText.textContent = 'Conectado';
        statusIndicator.classList.add('connected');
        statusIndicator.classList.remove('disconnected');
    } else {
        connectionCard.style.display = 'block';
        servicesGrid.style.display = 'none';
        serverInfoDisplay.style.display = 'none';
        statusText.textContent = 'Desconectado';
        statusIndicator.classList.remove('connected');
        statusIndicator.classList.add('disconnected');
    }
}

async function callApi(endpoint, data = {}) {
    if (!isConnected) {
        showToast('Você precisa se conectar primeiro.', 'error');
        return;
    }

    const payload = {
        ...credentials,
        ...data
    };

    log(`Chamando API: ${endpoint}...`, 'info');

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Erro desconhecido na API');
        }

        log(`Sucesso: ${result.message}`, 'success');
        showToast(result.message, 'success');

        // If there are detected stacks (like in portainer check), log them
        if (result.detected_stacks) {
            log(`Stacks detectadas: ${result.detected_stacks.join(', ')}`, 'info');
        }

        return result;
    } catch (error) {
        log(`Erro: ${error.message}`, 'error');
        showToast(`Erro: ${error.message}`, 'error');
        throw error;
    }
}

// Service Actions
async function installDocker() {
    const btn = document.getElementById('btn-install-docker');
    const originalText = btn ? btn.textContent : 'Instalar';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Iniciando...`;
    }

    try {
        await callApi('/install-docker');
        // Start polling
        pollInstallStatus('docker');
    } catch (e) {
        // Error already handled by callApi, but we need to revert button
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

async function initSwarm() {
    const btn = document.getElementById('btn-init-swarm');
    const originalText = btn ? btn.textContent : 'Inicializar';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Iniciando...`;
    }

    try {
        await callApi('/init-swarm');
        pollInstallStatus('swarm');
    } catch (e) {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

async function createNetwork() {
    const btn = document.getElementById('btn-create-network');
    const originalText = btn ? btn.textContent : 'Criar Rede';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Iniciando...`;
    }

    try {
        await callApi('/create-network', {
            network_name: 'network_swarm_public'
        });
        pollInstallStatus('network');
    } catch (e) {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

function pollInstallStatus(service) {
    let btnId = `btn-install-${service}`;
    let successText = 'Instalado';
    let loadingText = 'Instalando...';

    // Mapeamento de IDs e textos específicos
    if (service === 'swarm') {
        btnId = 'btn-init-swarm';
        successText = 'Ativo';
        loadingText = 'Inicializando...';
    } else if (service === 'network') {
        btnId = 'btn-create-network';
        successText = 'Criada';
        loadingText = 'Criando...';
    }

    const btn = document.getElementById(btnId);
    const originalText = btn ? btn.textContent : 'Ação';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${loadingText}`;
    }

    const intervalId = setInterval(async () => {
        try {
            const response = await fetch(`/install-status/${service}`);
            const result = await response.json();

            if (result.status === 'success') {
                clearInterval(intervalId);
                showSuccessModal(result.message);

                if (btn) {
                    btn.textContent = successText;
                    btn.classList.add('secondary');
                    btn.disabled = true; // Mantém desabilitado para Swarm/Network/Install
                }

                // Update System State locally
                if (service === 'docker') systemState.docker = true;
                if (service === 'swarm') systemState.swarm = true;
                if (service === 'network') systemState.network = true;

                // Add to installed services set
                installedServices.add(service);

                updateServiceButtons();

                log(`Ação ${service} concluída: ${result.message}`, 'success');
            } else if (result.status === 'error') {
                clearInterval(intervalId);
                showToast(`Erro: ${result.message}`, 'error');
                log(`Erro em ${service}: ${result.message}`, 'error');
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }
            }
        } catch (error) {
            console.error("Polling error:", error);
        }
    }, 2000);
}

function showSuccessModal(message) {
    document.getElementById('successMessage').textContent = message;
    document.getElementById('successModal').style.display = 'block';
}

function closeSuccessModal() {
    document.getElementById('successModal').style.display = 'none';
}

function installTraefik() {
    const email = document.getElementById('traefikEmail').value;
    if (!email) {
        showToast('Email é obrigatório para o Traefik (SSL).', 'error');
        return;
    }
    callApi('/install-traefik', { email });
}

function installPortainer() {
    const portainer_host = document.getElementById('portainerHost').value;
    if (!portainer_host) {
        showToast('Domínio do Portainer é obrigatório.', 'error');
        return;
    }
    callApi('/install-portainer', { portainer_host });
}

function installRedis() {
    const apiKey = prompt("Para instalar via Portainer (editável), insira sua API Key do Portainer.\nDeixe em branco para instalar via SSH (padrão/limitado).");

    const payload = {};
    if (apiKey && apiKey.trim() !== "") {
        payload.portainer_api_key = apiKey.trim();
    }

    callApi('/install-redis', payload);
}

function installPostgres() {
    const postgres_password = document.getElementById('postgresPwd').value;
    if (!postgres_password) {
        showToast('Senha do Postgres é obrigatória.', 'error');
        return;
    }
    callApi('/install-postgres', { postgres_password });
}

function installN8N() {
    const n8n_host = document.getElementById('n8nHost').value;
    const n8n_webhook_url = document.getElementById('n8nWebhook').value;
    const postgres_password = document.getElementById('postgresPwd').value; // Reuse postgres pwd field or ask for it

    if (!n8n_host || !n8n_webhook_url) {
        showToast('Domínio e Webhook URL são obrigatórios para N8N.', 'error');
        return;
    }
    if (!postgres_password) {
        showToast('Senha do Postgres é obrigatória (use o campo do Postgres).', 'error');
        return;
    }

    callApi('/install-n8n', { n8n_host, n8n_webhook_url, postgres_password });
}

function installChatwoot() {
    const chatwoot_base_url = document.getElementById('chatwootUrl').value;
    // Chatwoot requires many params. For simplicity in this UI demo, I'll hardcode or ask for more.
    // The API requires: postgres_password, minio_user, minio_password, minio_base_url_public, chatwoot_base_url
    // This is getting complex for a single card. I'll prompt for missing ones or use defaults/placeholders.

    // For now, let's just alert that it needs more info or implement a modal. 
    // To keep it simple, I'll assume the user fills the Postgres Pwd field and I'll use defaults for Minio if not provided, 
    // BUT the API requires them.

    // Let's just use prompt() for the missing ones for now to keep the UI simple but functional.
    const postgres_password = document.getElementById('postgresPwdChatwoot').value;
    const minio_user = document.getElementById('minioUserChatwoot').value;
    const minio_password = document.getElementById('minioPassChatwoot').value;
    const minio_base_url_public = document.getElementById('minioUrlChatwoot').value;

    if (!chatwoot_base_url || !postgres_password || !minio_user || !minio_password || !minio_base_url_public) {
        showToast('Preencha todos os campos do Chatwoot.', 'error');
        return;
    }

    callApi('/install-chatwoot', {
        postgres_password,
        minio_user,
        minio_password,
        minio_base_url_public,
        chatwoot_base_url
    });
}

function installRabbitMQ() {
    const rabbit_user = document.getElementById('rabbitUser').value;
    const rabbit_password = document.getElementById('rabbitPass').value;
    const rabbit_base_url = document.getElementById('rabbitUrl').value;

    if (!rabbit_user || !rabbit_password || !rabbit_base_url) {
        showToast('Preencha todos os campos do RabbitMQ.', 'error');
        return;
    }

    callApi('/install-rabbitmq', { rabbit_user, rabbit_password, rabbit_base_url });
}

function installMinio() {
    const minio_user = document.getElementById('minioUser').value;
    const minio_password = document.getElementById('minioPass').value;
    const minio_base_url_public = document.getElementById('minioUrlPublic').value;
    const minio_base_url_private = document.getElementById('minioUrlPrivate').value;

    if (!minio_user || !minio_password || !minio_base_url_public || !minio_base_url_private) {
        showToast('Preencha todos os campos do Minio.', 'error');
        return;
    }

    callApi('/install-minio', { minio_user, minio_password, minio_base_url_public, minio_base_url_private });
}

function installBaserow() {
    const baserow_base_url = document.getElementById('baserowUrl').value;
    const postgres_password = document.getElementById('postgresPwd').value;

    if (!baserow_base_url) {
        showToast('URL do Baserow é obrigatória.', 'error');
        return;
    }
    if (!postgres_password) {
        showToast('Senha do Postgres é obrigatória (use o campo do Postgres).', 'error');
        return;
    }

    callApi('/install-baserow', { baserow_base_url, postgres_password });
}

function restartStack(stackName) {
    if (confirm(`Tem certeza que deseja reiniciar a stack ${stackName}?`)) {
        callApi('/restart-stack', { stack_name: stackName });
    }
}

// Utilities
function log(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    const time = new Date().toLocaleTimeString();
    entry.textContent = `[${time}] ${message}`;
    logsContent.appendChild(entry);
    logsContent.scrollTop = logsContent.scrollHeight;
}

function clearLogs() {
    logsContent.innerHTML = '';
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = '';
    if (type === 'success') icon = '<i class="fa-solid fa-check-circle"></i>';
    if (type === 'error') icon = '<i class="fa-solid fa-exclamation-circle"></i>';

    toast.innerHTML = `${icon} <span>${message}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
