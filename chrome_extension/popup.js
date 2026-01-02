const API_URL = "http://localhost:8000";

// --- STATE & UTILS ---
let currentModalAction = null;
let pollInterval = null;

function log(msg, type = "info") {
    const logContainer = document.getElementById("log-container");
    const p = document.createElement("p");
    p.textContent = `> ${msg}`;
    if (type === "error") p.style.color = "#ef4444";
    if (type === "success") p.style.color = "#10b981";
    logContainer.prepend(p);

    if (type === "error") showToast(msg, "error");
    if (type === "success") showToast(msg, "success");
}

function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// --- PROGRESS OVERLAY ---
function showProgress(title, message = "Iniciando...") {
    const overlay = document.getElementById("progress-overlay");
    const titleEl = document.getElementById("progress-title");
    const msgEl = document.getElementById("progress-message");
    const spinner = document.getElementById("progress-spinner");
    const icon = document.getElementById("progress-icon");
    const btnClose = document.getElementById("btn-close-progress");

    titleEl.textContent = title;
    msgEl.textContent = message;

    // Reset state
    spinner.style.display = "block";
    icon.style.display = "none";
    icon.className = "";
    icon.innerHTML = "";
    btnClose.style.display = "none";
    overlay.style.display = "flex";
    document.body.style.overflow = "hidden"; // Disable scroll
}

function updateProgress(message) {
    const msgEl = document.getElementById("progress-message");
    msgEl.textContent = message;
}

function finishProgress(success, message) {
    const spinner = document.getElementById("progress-spinner");
    const icon = document.getElementById("progress-icon");
    const titleEl = document.getElementById("progress-title");
    const msgEl = document.getElementById("progress-message");
    const btnClose = document.getElementById("btn-close-progress");

    spinner.style.display = "none";
    icon.style.display = "flex";
    btnClose.style.display = "block";

    if (success) {
        icon.className = "progress-success-icon";
        icon.innerHTML = "✓";
        titleEl.textContent = "Concluído!";
    } else {
        icon.className = "progress-error-icon";
        icon.innerHTML = "✕";
        titleEl.textContent = "Erro";
    }
    msgEl.textContent = message;
}

function closeProgress() {
    const overlay = document.getElementById("progress-overlay");
    overlay.style.display = "none";
    document.body.style.overflow = "auto"; // Enable scroll
    if (pollInterval) clearInterval(pollInterval);
}

document.getElementById("btn-close-progress").addEventListener("click", closeProgress);

async function startInstallProcess(serviceKey, taskName, apiCallFunc) {
    showProgress(`Instalando ${taskName}...`, "Enviando solicitação ao servidor...");

    try {
        const res = await apiCallFunc();
        updateProgress("Instalação iniciada no servidor...");

        pollInterval = setInterval(async () => {
            try {
                const statusRes = await fetch(`${API_URL}/install-status/${serviceKey}`);
                const statusData = await statusRes.json();

                if (statusData.status === "success") {
                    clearInterval(pollInterval);
                    finishProgress(true, statusData.message || "Instalação concluída com sucesso.");
                    log(`${taskName} instalado com sucesso.`, "success");

                    // UX Improvement: Update button state immediately
                    const serviceToBtnMap = {
                        "docker": "btn-install-docker",
                        "swarm": "btn-init-swarm",
                        "network": "btn-create-network",
                        "ctop": "btn-install-ctop",
                        "traefik": "btn-open-traefik-modal",
                        "portainer": "btn-open-portainer-modal",
                        "redis": "btn-install-redis",
                        "postgres": "btn-open-postgres-modal",
                        "rabbitmq": "btn-open-rabbitmq-modal",
                        "minio": "btn-open-minio-modal",
                        "baserow": "btn-open-baserow-modal",
                        "n8n_editor": "btn-open-n8n-modal",
                        "chatwoot_admin": "btn-open-chatwoot-modal"
                    };

                    const btnId = serviceToBtnMap[serviceKey];
                    if (btnId) updateButtonState(btnId, true);

                    // Auto-refresh system status after installation
                    const creds = getCredentials(false);
                    if (creds) {
                        console.log("Auto-refreshing system status after installation...");
                        fetchSystemStatus(creds);
                    }

                } else if (statusData.status === "error") {
                    clearInterval(pollInterval);
                    finishProgress(false, statusData.message || "Erro desconhecido.");
                    log(`Erro ao instalar ${taskName}: ${statusData.message}`, "error");
                } else if (statusData.status === "running") {
                    updateProgress(statusData.message || "Instalando...");
                }
            } catch (e) {
                // Ignore poll errors
            }
        }, 2000);

    } catch (e) {
        finishProgress(false, e.message);
    }
}

// --- API ---

async function apiCall(endpoint, method = "POST", body = null, timeout = 60000) { // 60s timeout default
    try {
        const headers = { "Content-Type": "application/json" };
        const config = { method, headers };
        if (body) config.body = JSON.stringify(body);

        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), timeout);
        config.signal = controller.signal;

        const response = await fetch(`${API_URL}${endpoint}`, config);
        clearTimeout(id);

        if (!response) {
            throw new Error("Não foi possível conectar ao servidor local.");
        }

        const data = await response.json();

        if (!response.ok) {
            let errorMessage = "Erro na requisição";
            if (data.detail) {
                if (typeof data.detail === "string") {
                    errorMessage = data.detail;
                } else if (Array.isArray(data.detail)) {
                    // Pydantic validation errors generally
                    errorMessage = data.detail.map(e => `${e.loc ? e.loc.join(".") : ""} ${e.msg}`).join(", ");
                } else if (typeof data.detail === "object") {
                    errorMessage = JSON.stringify(data.detail);
                }
            }
            throw new Error(errorMessage);
        }
        return data;
    } catch (error) {
        if (error.name === 'AbortError') {
            const seconds = timeout / 1000;
            log(`Tempo limite de conexão excedido (${seconds}s).`, "error");
            throw new Error(`Tempo limite excedido (${seconds}s). O servidor demorou muito para responder.`);
        }
        log(error.message, "error");
        throw error;
    }
}

function getCredentials(showError = true) {
    const host = document.getElementById("host").value;
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    if (!host || !username || !password) {
        if (showError) log("Por favor, preencha as credenciais aba Conexão.", "error");
        return null;
    }
    return { host, username, password };
}

// --- SIDEBAR STATE MANAGEMENT ---
function disableSidebarButtons() {
    const sidebarItems = document.querySelectorAll('.sidebar-item');
    sidebarItems.forEach(item => {
        if (item.dataset.tab !== 'connection') {
            item.classList.add('disabled');
        }
    });
}

function enableSidebarButton(tabId) {
    const sidebarItems = document.querySelectorAll('.sidebar-item');
    sidebarItems.forEach(item => {
        if (item.dataset.tab === tabId) {
            item.classList.remove('disabled');
        }
    });
}

function enableAllSidebarButtons() {
    const sidebarItems = document.querySelectorAll('.sidebar-item');
    sidebarItems.forEach(item => {
        item.classList.remove('disabled');
    });
}

function saveCredentialsInStorage() {
    if (document.getElementById("save-creds").checked) {
        const creds = getCredentials(false);
        if (creds) {
            chrome.storage.local.set({ server_creds: creds }, () => { });
        }
    }
}

function loadCredentialsFromStorage() {
    chrome.storage.local.get(["server_creds"], (result) => {
        if (result.server_creds) {
            document.getElementById("host").value = result.server_creds.host;
            document.getElementById("username").value = result.server_creds.username;
            document.getElementById("password").value = result.server_creds.password;
            document.getElementById("save-creds").checked = true;
        }
    });
}

// --- TABS & SIDEBAR ---
document.querySelectorAll(".sidebar-item").forEach(item => {
    item.addEventListener("click", () => {
        document.querySelectorAll(".sidebar-item").forEach(i => i.classList.remove("active"));
        item.classList.add("active");

        document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
        const tabId = item.dataset.tab;
        document.getElementById(tabId).classList.add("active");
    });
});

document.getElementById("btn-verify").addEventListener("click", async () => {
    // 1. Setup
    const btn = document.getElementById("btn-verify");
    if (btn.disabled) return;

    const creds = getCredentials();
    if (!creds) return;

    saveCredentialsInStorage();

    btn.textContent = "Conectando...";
    btn.disabled = true;
    btn.classList.add("btn-disabled");
    console.log("Starting quick connection check...");

    try {
        // 2. Quick Connection Check (Login Only)
        // Aumentando timeout para 30s para garantir
        await apiCall("/verify-connection", "POST", creds, 30000);

        log("Conectado! Verificando serviços...", "success");
        document.getElementById("connection-status-text").textContent = "Conectado a " + creds.host;
        document.getElementById("connection-status-text").style.color = "#10b981";

        // Enable Status button after successful connection
        enableSidebarButton('tab-status');

        // Switch tab immediately
        document.querySelector('[data-tab="tab-status"]').click();

        // Show loading state in status list
        const statusList = document.getElementById("full-status-list");
        statusList.innerHTML = "<p style='color: #94a3b8; text-align: center;'>Carregando status do sistema...</p>";

        // Unlock "Connect" button immediately (reset text)
        btn.textContent = "Conectar e Verificar";
        btn.disabled = false;
        btn.classList.remove("btn-disabled");

        // 3. Heavy Status Check (Async)
        fetchSystemStatus(creds);

    } catch (e) {
        console.error("Connection failed:", e);
        document.getElementById("connection-status-text").textContent = "Erro na conexão";
        document.getElementById("connection-status-text").style.color = "#ef4444";
        log(e.message, "error");

        // Reset button only on error
        btn.textContent = "Conectar e Verificar";
        btn.disabled = false;
        btn.classList.remove("btn-disabled");
    }
});

async function fetchSystemStatus(creds) {
    try {
        console.log("Fetching full system status...");
        // Call heavy endpoint (60s timeout)
        const res = await apiCall("/system-status", "POST", creds, 60000);

        // Enable all sidebar buttons after system status loads
        enableAllSidebarButtons();

        // Update UI with heavy data
        const statusList = document.getElementById("full-status-list");
        statusList.innerHTML = ""; // Clear loading

        const addStatusItem = (name, isRunning, details = "") => {
            const div = document.createElement("div");
            div.className = "status-item";
            div.innerHTML = `
                <div class="status-name">${name}</div>
                <div class="status-badge ${isRunning ? 'running' : 'stopped'}">
                    ${isRunning ? 'Ativo' : 'Inativo'} ${details ? `(${details})` : ''}
                </div>
            `;
            statusList.appendChild(div);
        };

        addStatusItem("Docker", !!res.system_status.docker, res.system_status.docker);
        addStatusItem("Swarm Cluster", res.system_status.swarm);
        addStatusItem("Rede Overlay", res.system_status.network);
        addStatusItem("Ctop", res.system_status.ctop);

        const stacks = res.detected_stacks || [];
        const appMap = {
            "Traefik": "traefik",
            "Portainer": "portainer",
            "Redis": "redis",
            "Postgres": "postgres",
            "RabbitMQ": "rabbitmq",
            "Minio": "minio",
            "Baserow": "baserow",
            "N8N": "n8n_editor",
            "Chatwoot": "chatwoot_admin"
        };

        for (const [displayName, stackKey] of Object.entries(appMap)) {
            const isInstalled = stacks.includes(stackKey);
            addStatusItem(displayName, isInstalled);
        }


        // Enable buttons based on status
        updateButtonState("btn-install-docker", !!res.system_status.docker);
        updateButtonState("btn-init-swarm", res.system_status.swarm);
        updateButtonState("btn-create-network", res.system_status.network);
        updateButtonState("btn-install-ctop", res.system_status.ctop);

        // Infrastructure dependency chain: Docker → Swarm → Network
        const dockerInstalled = !!res.system_status.docker;
        const swarmActive = res.system_status.swarm;
        const networkCreated = res.system_status.network;

        // Swarm depends on Docker
        const swarmBtn = document.getElementById("btn-init-swarm");
        if (!swarmActive && swarmBtn) {
            if (!dockerInstalled) {
                swarmBtn.disabled = true;
                swarmBtn.style.opacity = "0.4";
                swarmBtn.style.cursor = "not-allowed";
                swarmBtn.title = "Instale o Docker primeiro";
            } else {
                swarmBtn.disabled = false;
                swarmBtn.style.opacity = "1";
                swarmBtn.style.cursor = "pointer";
                swarmBtn.title = "";
            }
        }

        // Network depends on Swarm
        const networkBtn = document.getElementById("btn-create-network");
        if (!networkCreated && networkBtn) {
            if (!swarmActive) {
                networkBtn.disabled = true;
                networkBtn.style.opacity = "0.4";
                networkBtn.style.cursor = "not-allowed";
                networkBtn.title = "Inicie o Swarm primeiro";
            } else {
                networkBtn.disabled = false;
                networkBtn.style.opacity = "1";
                networkBtn.style.cursor = "pointer";
                networkBtn.title = "";
            }
        }

        // Ctop depends on Network
        const ctopBtn = document.getElementById("btn-install-ctop");
        const ctopInstalled = res.system_status.ctop;
        if (!ctopInstalled && ctopBtn) {
            if (!networkCreated) {
                ctopBtn.disabled = true;
                ctopBtn.style.opacity = "0.4";
                ctopBtn.style.cursor = "not-allowed";
                ctopBtn.title = "Crie a Rede primeiro";
            } else {
                ctopBtn.disabled = false;
                ctopBtn.style.opacity = "1";
                ctopBtn.style.cursor = "pointer";
                ctopBtn.title = "";
            }
        }

        const btnMap = {
            "traefik": "btn-open-traefik-modal",
            "portainer": "btn-open-portainer-modal",
            "redis": "btn-install-redis",
            "postgres": "btn-open-postgres-modal",
            "rabbitmq": "btn-open-rabbitmq-modal",
            "minio": "btn-open-minio-modal",
            "baserow": "btn-open-baserow-modal",
            "n8n_editor": "btn-open-n8n-modal",
            "chatwoot_admin": "btn-open-chatwoot-modal"
        };


        for (const [stackName, btnId] of Object.entries(btnMap)) {
            const isInstalled = stacks.includes(stackName);
            updateButtonState(btnId, isInstalled);
        }

        // Core Apps dependency chain: Network → Traefik → Portainer
        const traefikInstalled = stacks.includes("traefik");
        const portainerInstalled = stacks.includes("portainer");

        // Traefik depends on Network
        const traefikBtn = document.getElementById("btn-open-traefik-modal");
        if (!traefikInstalled && traefikBtn) {
            if (!networkCreated) {
                traefikBtn.disabled = true;
                traefikBtn.style.opacity = "0.4";
                traefikBtn.style.cursor = "not-allowed";
                traefikBtn.title = "Crie a Rede primeiro";
            } else {
                traefikBtn.disabled = false;
                traefikBtn.style.opacity = "1";
                traefikBtn.style.cursor = "pointer";
                traefikBtn.title = "";
            }
        }

        // Portainer depends on Traefik
        const portainerBtn = document.getElementById("btn-open-portainer-modal");
        if (!portainerInstalled && portainerBtn) {
            if (!traefikInstalled) {
                portainerBtn.disabled = true;
                portainerBtn.style.opacity = "0.4";
                portainerBtn.style.cursor = "not-allowed";
                portainerBtn.title = "Instale o Traefik primeiro";
            } else {
                portainerBtn.disabled = false;
                portainerBtn.style.opacity = "1";
                portainerBtn.style.cursor = "pointer";
                portainerBtn.title = "";
            }
        }

        // Database services depend on Portainer
        const redisInstalled = stacks.includes("redis");
        const postgresInstalled = stacks.includes("postgres");

        // Redis depends on Portainer
        const redisBtn = document.getElementById("btn-install-redis");
        if (!redisInstalled && redisBtn) {
            if (!portainerInstalled) {
                redisBtn.disabled = true;
                redisBtn.style.opacity = "0.4";
                redisBtn.style.cursor = "not-allowed";
                redisBtn.title = "Instale o Portainer primeiro";
            } else {
                redisBtn.disabled = false;
                redisBtn.style.opacity = "1";
                redisBtn.style.cursor = "pointer";
                redisBtn.title = "";
            }
        }

        // Postgres depends on Portainer
        const postgresBtn = document.getElementById("btn-open-postgres-modal");
        if (!postgresInstalled && postgresBtn) {
            if (!portainerInstalled) {
                postgresBtn.disabled = true;
                postgresBtn.style.opacity = "0.4";
                postgresBtn.style.cursor = "not-allowed";
                postgresBtn.title = "Instale o Portainer primeiro";
            } else {
                postgresBtn.disabled = false;
                postgresBtn.style.opacity = "1";
                postgresBtn.style.cursor = "pointer";
                postgresBtn.title = "";
            }
        }



        // Applications depend on Portainer (except Chatwoot which depends on Minio)
        const baserowInstalled = stacks.includes("baserow");
        const n8nInstalled = stacks.includes("n8n_editor");
        const rabbitmqInstalled = stacks.includes("rabbitmq");
        const minioInstalled = stacks.includes("minio");

        // Baserow depends on Postgres
        const baserowBtn = document.getElementById("btn-open-baserow-modal");
        if (!baserowInstalled && baserowBtn) {
            if (!postgresInstalled) {
                baserowBtn.disabled = true;
                baserowBtn.style.opacity = "0.4";
                baserowBtn.style.cursor = "not-allowed";
                baserowBtn.title = "Instale o Postgres primeiro";
            } else {
                baserowBtn.disabled = false;
                baserowBtn.style.opacity = "1";
                baserowBtn.style.cursor = "pointer";
                baserowBtn.title = "";
            }
        }

        // N8N depends on Postgres
        const n8nBtn = document.getElementById("btn-open-n8n-modal");
        if (!n8nInstalled && n8nBtn) {
            if (!postgresInstalled) {
                n8nBtn.disabled = true;
                n8nBtn.style.opacity = "0.4";
                n8nBtn.style.cursor = "not-allowed";
                n8nBtn.title = "Instale o Postgres primeiro";
            } else {
                n8nBtn.disabled = false;
                n8nBtn.style.opacity = "1";
                n8nBtn.style.cursor = "pointer";
                n8nBtn.title = "";
            }
        }

        // RabbitMQ depends on Portainer
        const rabbitmqBtn = document.getElementById("btn-open-rabbitmq-modal");
        if (!rabbitmqInstalled && rabbitmqBtn) {
            if (!portainerInstalled) {
                rabbitmqBtn.disabled = true;
                rabbitmqBtn.style.opacity = "0.4";
                rabbitmqBtn.style.cursor = "not-allowed";
                rabbitmqBtn.title = "Instale o Portainer primeiro";
            } else {
                rabbitmqBtn.disabled = false;
                rabbitmqBtn.style.opacity = "1";
                rabbitmqBtn.style.cursor = "pointer";
                rabbitmqBtn.title = "";
            }
        }

        // Minio depends on Portainer
        const minioBtn = document.getElementById("btn-open-minio-modal");
        if (!minioInstalled && minioBtn) {
            if (!portainerInstalled) {
                minioBtn.disabled = true;
                minioBtn.style.opacity = "0.4";
                minioBtn.style.cursor = "not-allowed";
                minioBtn.title = "Instale o Portainer primeiro";
            } else {
                minioBtn.disabled = false;
                minioBtn.style.opacity = "1";
                minioBtn.style.cursor = "pointer";
                minioBtn.title = "";
            }
        }



        // Dependency: Chatwoot requires Minio to be installed first
        const chatwootInstalled = stacks.includes("chatwoot_admin");
        const chatwootBtn = document.getElementById("btn-open-chatwoot-modal");


        // Only apply dependency if Chatwoot is NOT already installed
        if (!chatwootInstalled && chatwootBtn) {
            if (!minioInstalled) {
                chatwootBtn.disabled = true;
                chatwootBtn.style.opacity = "0.4";
                chatwootBtn.style.cursor = "not-allowed";
                chatwootBtn.title = "Instale o Minio primeiro";
            } else {
                // Minio installed, enable Chatwoot button
                chatwootBtn.disabled = false;
                chatwootBtn.style.opacity = "1";
                chatwootBtn.style.cursor = "pointer";
                chatwootBtn.title = "";
            }
        }

        log("Status do sistema atualizado.", "success");



    } catch (e) {
        console.error("Status fetch failed:", e);
        log("Falha ao atualizar status: " + e.message, "error");
        document.getElementById("full-status-list").innerHTML = "<p style='color: #ef4444; text-align: center;'>Erro ao carregar status.</p>";
    }
}

function updateButtonState(btnId, isInstalled) {
    const btn = document.getElementById(btnId);
    if (!btn) return;

    if (isInstalled) {
        if (btn.textContent === "Instalar") btn.textContent = "Instalado";
        if (btn.textContent === "Iniciar") btn.textContent = "Ativo";
        if (btn.textContent === "Criar") btn.textContent = "Criada";
        if (btn.textContent === "Configurar") btn.textContent = "Configurado";

        btn.classList.add("btn-disabled");
    } else {
        // Prevent reverting to active state if it's already marked as done
        const doneStates = ["Instalado", "Ativo", "Criada", "Configurado"];
        if (doneStates.includes(btn.textContent)) {
            // Keep it disabled
            btn.classList.add("btn-disabled");
        } else {
            btn.classList.remove("btn-disabled");
        }
    }
}

// --- MODAL SYSTEM ---
const modalOverlay = document.getElementById("modal-overlay");
const modalTitle = document.getElementById("modal-title");
const modalContent = document.getElementById("modal-content");
const btnCancelModal = document.getElementById("btn-cancel-modal");
const btnConfirmModal = document.getElementById("btn-confirm-modal");

function openModal(title, fields, onConfirm) {
    const creds = getCredentials(false);
    if (!creds) {
        // If not connected, force user to connection tab or show error
        showToast("Conecte-se ao servidor primeiro!", "error");
        document.querySelector('[data-tab="tab-connection"]').click();
        return;
    }

    modalTitle.textContent = title;
    modalContent.innerHTML = "";
    currentModalAction = onConfirm;

    fields.forEach(field => {
        const div = document.createElement("div");
        div.className = "input-group";

        const label = document.createElement("label");
        label.textContent = field.label;
        div.appendChild(label);

        let input;
        if (field.type === "select") {
            input = document.createElement("select");
            input.className = "styled-select";
            input.innerHTML = '<option value="">Carregando...</option>';
        } else {
            input = document.createElement("input");
            input.type = field.type || "text";
            input.placeholder = field.placeholder || '';
            if (field.value) input.value = field.value;
        }

        input.id = field.id;
        div.appendChild(input);
        modalContent.appendChild(div);
    });

    modalOverlay.style.display = "flex";
}

function closeModal() {
    modalOverlay.style.display = "none";
    currentModalAction = null;
}

btnCancelModal.addEventListener("click", closeModal);

btnConfirmModal.addEventListener("click", () => {
    if (currentModalAction) {
        currentModalAction();
        closeModal();
    }
});

// --- BUTTON LISTENERS ---

// Base
document.getElementById("btn-install-docker").addEventListener("click", () => {
    const creds = getCredentials();
    if (!creds) return;
    startInstallProcess("docker", "Docker", () => apiCall("/install-docker", "POST", creds));
});

document.getElementById("btn-init-swarm").addEventListener("click", () => {
    const creds = getCredentials();
    if (!creds) return;
    startInstallProcess("swarm", "Swarm", () => apiCall("/init-swarm", "POST", creds));
});

document.getElementById("btn-create-network").addEventListener("click", () => {
    const creds = getCredentials();
    if (!creds) return;
    startInstallProcess("network", "Rede Overlay", () => apiCall("/create-network", "POST", creds));
});

document.getElementById("btn-install-ctop").addEventListener("click", () => {
    const creds = getCredentials();
    if (!creds) return;
    startInstallProcess("ctop", "Ctop", () => apiCall("/install-ctop", "POST", creds));
});

// Traefik
document.getElementById("btn-open-traefik-modal").addEventListener("click", () => {
    openModal("Configurar Traefik", [
        { label: "Email para Let's Encrypt", id: "traefik_email", placeholder: "admin@exemplo.com" }
    ], () => {
        const email = document.getElementById("traefik_email").value;
        const creds = getCredentials();
        if (!email) return showToast("Email é obrigatório", "error");
        startInstallProcess("traefik", "Traefik", () => apiCall("/install-traefik", "POST", { ...creds, email }));
    });
});

// Portainer
document.getElementById("btn-open-portainer-modal").addEventListener("click", () => {
    openModal("Configurar Portainer", [
        { label: "Zona Cloudflare", id: "portainer_zone", type: "select" },
        { label: "DNS Portainer", id: "portainer_dns", type: "select" }
    ], () => {
        const domain = document.getElementById("portainer_dns").value;
        const creds = getCredentials();

        if (!domain) return showToast("Selecione um DNS", "error");

        startInstallProcess("portainer", "Portainer", () => apiCall("/install-portainer", "POST", {
            ...creds,
            portainer_host: domain
        }));
    });

    setTimeout(() => setupDnsSelectors("portainer_zone", "portainer_dns"), 100);
});

// Postgres
document.getElementById("btn-open-postgres-modal").addEventListener("click", () => {
    // Check for saved password first
    chrome.storage.local.get(["saved_postgres_password"], (result) => {
        const savedPass = result.saved_postgres_password || "";

        openModal("Configurar Postgres", [
            { label: "Senha DB", id: "postgres-password", type: "password", value: savedPass }
        ], () => {
            const password = document.getElementById("postgres-password").value;
            const creds = getCredentials();

            if (!password) return showToast("Senha é obrigatória", "error");

            // Save password for other apps
            chrome.storage.local.set({ saved_postgres_password: password });

            startInstallProcess("postgres", "Postgres", () => apiCall("/install-postgres", "POST", {
                ...creds,
                postgres_user: "postgres",
                postgres_password: password,
                postgres_db: "app_db"
            }));
        });
    });
});

// Redis
// Redis
document.getElementById("btn-install-redis").addEventListener("click", () => {
    // Revertido para instalação direta (sem modal de API Key)
    const creds = getCredentials();
    startInstallProcess("redis", "Redis", () => apiCall("/install-redis", "POST", {
        ...creds
    }));
});

// RabbitMQ
document.getElementById("btn-open-rabbitmq-modal").addEventListener("click", () => {
    openModal("Configurar RabbitMQ", [
        { label: "Zona Cloudflare", id: "rabbitmq_zone", type: "select" },
        { label: "DNS RabbitMQ (Opcional)", id: "rabbitmq_dns", type: "select" },
        { label: "Usuário", id: "rmq_user", placeholder: "admin", value: "admin" },
        { label: "Senha", id: "rmq_password", type: "password" }
    ], () => {
        const user = document.getElementById("rmq_user").value;
        const password = document.getElementById("rmq_password").value;
        const domain = document.getElementById("rabbitmq_dns").value;
        const creds = getCredentials();

        if (!user || !password) return showToast("Usuário e Senha são obrigatórios", "error");

        const payload = {
            ...creds,
            rabbit_user: user,
            rabbit_password: password,
            rabbit_base_url: domain || ""
        };

        startInstallProcess("rabbitmq", "RabbitMQ", () => apiCall("/install-rabbitmq", "POST", payload));
    });

    setTimeout(() => setupDnsSelectors("rabbitmq_zone", "rabbitmq_dns"), 100);
});

// Minio
document.getElementById("btn-open-minio-modal").addEventListener("click", () => {
    openModal("Configurar Minio", [
        { label: "Usuário Root", id: "minio_user", placeholder: "admin", value: "admin" },
        { label: "Senha Root", id: "minio_curr_password", type: "password" },
        { label: "Domínio Console (ex: s3-console.dom.com)", id: "minio_console_domain" },
        { label: "Domínio API (ex: s3-api.dom.com)", id: "minio_api_domain" }
    ], () => {
        const user = document.getElementById("minio_user").value;
        const password = document.getElementById("minio_curr_password").value;
        const consoleDomain = document.getElementById("minio_console_domain").value;
        const apiDomain = document.getElementById("minio_api_domain").value;
        const creds = getCredentials();

        if (!user || !password || !consoleDomain || !apiDomain)
            return showToast("Preencha todos os campos", "error");

        const payload = {
            ...creds,
            minio_user: user,
            minio_password: password,
            minio_base_url_public: consoleDomain,
            minio_base_url_private: apiDomain
        };
        console.log("Installing Minio", payload);

        startInstallProcess("minio", "Minio", () => apiCall("/install-minio", "POST", payload));
    });
});

// --- CLOUDFLARE DNS MANAGER (END) ---

// --- REUSABLE DNS SELECTOR FOR APP MODALS ---
async function setupDnsSelectors(zoneSelectId, dnsSelectId, onReady = null) {
    const zoneSelect = document.getElementById(zoneSelectId);
    const dnsSelect = document.getElementById(dnsSelectId);

    if (!zoneSelect || !dnsSelect) {
        console.error("DNS selectors not found:", zoneSelectId, dnsSelectId);
        return;
    }

    // Get Cloudflare API token
    const tokenResult = await new Promise(resolve => chrome.storage.local.get(["cf_api_token"], resolve));
    const token = tokenResult.cf_api_token;

    if (!token) {
        zoneSelect.innerHTML = '<option value="">Token Cloudflare não configurado</option>';
        dnsSelect.innerHTML = '<option value="">Configure o token primeiro</option>';
        return;
    }

    // Get server IP
    const serverIp = document.getElementById("host")?.value;
    if (!serverIp) {
        zoneSelect.innerHTML = '<option value="">Conecte ao servidor primeiro</option>';
        return;
    }

    // Load zones
    try {
        const res = await apiCall("/cloudflare/zones", "POST", { api_token: token });

        zoneSelect.innerHTML = '<option value="">Selecione a zona...</option>';
        res.zones.forEach(zone => {
            const opt = document.createElement("option");
            opt.value = zone.id;
            opt.textContent = zone.name;
            opt.dataset.name = zone.name;
            zoneSelect.appendChild(opt);
        });

        // Zone change handler
        zoneSelect.onchange = async () => {
            const zoneId = zoneSelect.value;
            const zoneName = zoneSelect.options[zoneSelect.selectedIndex]?.dataset.name;

            if (!zoneId) {
                dnsSelect.innerHTML = '<option value="">Selecione a zona primeiro</option>';
                return;
            }

            dnsSelect.innerHTML = '<option value="">Carregando...</option>';

            try {
                const dnsRes = await apiCall("/cloudflare/records", "POST", {
                    api_token: token,
                    zone_id: zoneId,
                    ip_filter: serverIp
                });

                dnsSelect.innerHTML = '<option value="">Selecione o DNS...</option>';

                if (dnsRes.records && dnsRes.records.length > 0) {
                    dnsRes.records.forEach(record => {
                        const opt = document.createElement("option");
                        opt.value = record.name;
                        opt.textContent = `${record.name} ${record.proxied ? '☁️' : '🛡️'}`;
                        dnsSelect.appendChild(opt);
                    });

                    if (onReady) onReady();
                } else {
                    dnsSelect.innerHTML = '<option value="">Nenhum DNS encontrado para este IP</option>';
                }
            } catch (e) {
                dnsSelect.innerHTML = `<option value="">Erro: ${e.message}</option>`;
            }
        };

    } catch (e) {
        zoneSelect.innerHTML = `<option value="">Erro ao carregar zonas: ${e.message}</option>`;
    }
}

// --- APP CONFIGURATIONS ---
document.getElementById("btn-open-baserow-modal").addEventListener("click", async () => {
    // Get saved password
    const stored = await new Promise(r => chrome.storage.local.get(["saved_postgres_password"], r));
    const savedPass = stored.saved_postgres_password || "";

    openModal("Configurar Baserow", [
        { label: "Zona Cloudflare", id: "baserow_zone", type: "select" },
        { label: "DNS Record", id: "baserow_dns", type: "select" },
        { label: "Senha Postgres", id: "baserow_postgres_password", type: "password", value: savedPass }
    ], () => {
        const domain = document.getElementById("baserow_dns").value;
        const postgresPassword = document.getElementById("baserow_postgres_password").value;
        const creds = getCredentials();

        if (!domain) return showToast("Selecione um DNS", "error");
        if (!postgresPassword) return showToast("Informe a senha do Postgres", "error");

        startInstallProcess("baserow", "Baserow", () => apiCall("/install-baserow", "POST", {
            ...creds,
            domain: domain,
            baserow_base_url: `https://${domain}`,
            postgres_password: postgresPassword
        }));
    });

    // Setup DNS selectors after modal opens
    setTimeout(() => setupDnsSelectors("baserow_zone", "baserow_dns"), 100);
});

// N8N
document.getElementById("btn-open-n8n-modal").addEventListener("click", async () => {
    // Get saved password
    const stored = await new Promise(r => chrome.storage.local.get(["saved_postgres_password"], r));
    const savedPass = stored.saved_postgres_password || "";

    openModal("Configurar N8N", [
        { label: "Zona Cloudflare", id: "n8n_zone", type: "select" },
        { label: "DNS N8N (Interface)", id: "n8n_dns", type: "select" },
        { label: "DNS Webhook", id: "n8n_webhook_dns", type: "select" },
        { label: "Senha Postgres", id: "n8n_postgres_password", type: "password", value: savedPass }
    ], () => {
        const domain = document.getElementById("n8n_dns").value;
        const webhookDomain = document.getElementById("n8n_webhook_dns").value;
        const postgresPassword = document.getElementById("n8n_postgres_password").value;
        const creds = getCredentials();

        if (!domain || !webhookDomain || !postgresPassword) {
            return showToast("Preencha todos os campos", "error");
        }

        startInstallProcess("n8n_editor", "N8N", () => apiCall("/install-n8n", "POST", {
            ...creds,
            domain: domain,
            n8n_host: `https://${domain}`,
            n8n_webhook_url: `https://${webhookDomain}`,
            postgres_password: postgresPassword
        }));
    });

    setTimeout(() => {
        setupDnsSelectors("n8n_zone", "n8n_dns");
        // Setup webhook DNS selector (reusing zone)
        document.getElementById("n8n_zone").addEventListener("change", async () => {
            const zoneId = document.getElementById("n8n_zone").value;
            const webhookDnsSelect = document.getElementById("n8n_webhook_dns");
            const token = (await new Promise(r => chrome.storage.local.get(["cf_api_token"], r))).cf_api_token;
            const serverIp = document.getElementById("host")?.value;

            if (zoneId && token && serverIp) {
                webhookDnsSelect.innerHTML = '<option value="">Carregando...</option>';
                try {
                    const res = await apiCall("/cloudflare/records", "POST", {
                        api_token: token,
                        zone_id: zoneId,
                        ip_filter: serverIp
                    });
                    webhookDnsSelect.innerHTML = '<option value="">Selecione DNS Webhook...</option>';
                    if (res.records && res.records.length > 0) {
                        res.records.forEach(record => {
                            const opt = document.createElement("option");
                            opt.value = record.name;
                            opt.textContent = `${record.name} ${record.proxied ? '☁️' : '🛡️'}`;
                            webhookDnsSelect.appendChild(opt);
                        });
                    }
                } catch (e) {
                    webhookDnsSelect.innerHTML = `<option value="">Erro: ${e.message}</option>`;
                }
            }
        });
    }, 100);
});

// Minio
document.getElementById("btn-open-minio-modal").addEventListener("click", async () => {
    // Get saved credentials
    const stored = await new Promise(r => chrome.storage.local.get(["saved_minio_user", "saved_minio_password"], r));
    const savedUser = stored.saved_minio_user || "admin";
    const savedPass = stored.saved_minio_password || "";

    openModal("Configurar Minio", [
        { label: "Zona Cloudflare", id: "minio_zone", type: "select" },
        { label: "DNS para API", id: "minio_dns", type: "select" },
        { label: "DNS para Console", id: "minio_console_dns", type: "select" },
        { label: "Usuário Minio", id: "minio_user", placeholder: "admin", value: savedUser },
        { label: "Senha Minio", id: "minio_password", type: "password", value: savedPass }
    ], () => {
        const domain = document.getElementById("minio_dns").value;
        const consoleDomain = document.getElementById("minio_console_dns").value;
        const minioUser = document.getElementById("minio_user").value;
        const minioPassword = document.getElementById("minio_password").value;
        const creds = getCredentials();

        if (!domain || !consoleDomain || !minioUser || !minioPassword) {
            return showToast("Preencha todos os campos", "error");
        }

        // Save credentials for other apps (like Chatwoot)
        chrome.storage.local.set({
            saved_minio_user: minioUser,
            saved_minio_password: minioPassword
        });

        startInstallProcess("minio", "Minio", () => apiCall("/install-minio", "POST", {
            ...creds,
            domain: domain,
            console_domain: consoleDomain,
            minio_user: minioUser,
            minio_password: minioPassword,
            minio_base_url_private: consoleDomain,
            minio_base_url_public: domain
        }));
    });

    setTimeout(() => {
        setupDnsSelectors("minio_zone", "minio_dns");

        // Setup console DNS selector (reusing same logic)
        document.getElementById("minio_zone").addEventListener("change", async () => {
            const zoneId = document.getElementById("minio_zone").value;
            const consoleDnsSelect = document.getElementById("minio_console_dns");
            const token = (await new Promise(r => chrome.storage.local.get(["cf_api_token"], r))).cf_api_token;
            const serverIp = document.getElementById("host")?.value;

            if (zoneId && token && serverIp) {
                consoleDnsSelect.innerHTML = '<option value="">Carregando...</option>';
                try {
                    const res = await apiCall("/cloudflare/records", "POST", {
                        api_token: token,
                        zone_id: zoneId,
                        ip_filter: serverIp
                    });
                    consoleDnsSelect.innerHTML = '<option value="">Selecione DNS Console...</option>';
                    if (res.records && res.records.length > 0) {
                        res.records.forEach(record => {
                            const opt = document.createElement("option");
                            opt.value = record.name;
                            opt.textContent = `${record.name} ${record.proxied ? '☁️' : '🛡️'}`;
                            consoleDnsSelect.appendChild(opt);
                        });
                    }
                } catch (e) {
                    consoleDnsSelect.innerHTML = `<option value="">Erro: ${e.message}</option>`;
                }
            }
        });
    }, 100);
});


// Chatwoot
document.getElementById("btn-open-chatwoot-modal").addEventListener("click", async () => {
    // Get saved password and minio creds
    const stored = await new Promise(r => chrome.storage.local.get(["saved_postgres_password", "saved_minio_user", "saved_minio_password"], r));
    const savedPgPass = stored.saved_postgres_password || "";
    const savedMinioUser = stored.saved_minio_user || "admin";
    const savedMinioPass = stored.saved_minio_password || "";

    openModal("Configurar Chatwoot", [
        { label: "Zona Cloudflare", id: "chatwoot_zone", type: "select" },
        { label: "DNS Chatwoot", id: "chatwoot_dns", type: "select" },
        { label: "DNS Minio API", id: "chatwoot_minio_dns", type: "select" },
        { label: "Senha Postgres", id: "chatwoot_postgres_password", type: "password", value: savedPgPass },
        { label: "Usuário Minio", id: "chatwoot_minio_user", placeholder: "admin", value: savedMinioUser },
        { label: "Senha Minio", id: "chatwoot_minio_password", type: "password", value: savedMinioPass }
    ], () => {
        const domain = document.getElementById("chatwoot_dns").value;
        const minioDns = document.getElementById("chatwoot_minio_dns").value;
        const postgresPassword = document.getElementById("chatwoot_postgres_password").value;
        const minioUser = document.getElementById("chatwoot_minio_user").value;
        const minioPassword = document.getElementById("chatwoot_minio_password").value;
        const creds = getCredentials();

        if (!domain || !minioDns || !postgresPassword || !minioUser || !minioPassword) {
            return showToast("Preencha todos os campos", "error");
        }

        startInstallProcess("chatwoot_admin", "Chatwoot", () => apiCall("/install-chatwoot", "POST", {
            ...creds,
            domain: domain,
            chatwoot_base_url: `https://${domain}`,
            postgres_password: postgresPassword,
            minio_user: minioUser,
            minio_password: minioPassword,
            minio_base_url_public: `https://${minioDns}`
        }));
    });

    setTimeout(() => {
        setupDnsSelectors("chatwoot_zone", "chatwoot_dns");
        // Setup second DNS selector for Minio (reusing zone)
        document.getElementById("chatwoot_zone").addEventListener("change", async () => {
            const zoneId = document.getElementById("chatwoot_zone").value;
            const minioDnsSelect = document.getElementById("chatwoot_minio_dns");
            const token = (await new Promise(r => chrome.storage.local.get(["cf_api_token"], r))).cf_api_token;
            const serverIp = document.getElementById("host")?.value;

            if (zoneId && token && serverIp) {
                minioDnsSelect.innerHTML = '<option value="">Carregando Minio DNS...</option>';
                try {
                    const res = await apiCall("/cloudflare/records", "POST", {
                        api_token: token,
                        zone_id: zoneId,
                        ip_filter: serverIp
                    });
                    minioDnsSelect.innerHTML = '<option value="">Selecione DNS Minio...</option>';
                    if (res.records && res.records.length > 0) {
                        res.records.forEach(record => {
                            const opt = document.createElement("option");
                            opt.value = record.name;
                            opt.textContent = `${record.name} ${record.proxied ? '☁️' : '🛡️'}`;
                            minioDnsSelect.appendChild(opt);
                        });
                    }
                } catch (e) {
                    minioDnsSelect.innerHTML = `<option value="">Erro: ${e.message}</option>`;
                }
            }
        });
    }, 100);
});


// --- CLOUDFLARE DNS LOGIC ---

const cfTokenSection = document.getElementById("dns-token-section");
const dnsManagerSection = document.getElementById("dns-manager-section");
const cfTokenInput = document.getElementById("cf-api-token");
const cfZoneSelect = document.getElementById("cf-zone-select");
const cfRecordContent = document.getElementById("cf-record-content");

// Check for token on load
chrome.storage.local.get(["cf_api_token"], (result) => {
    if (result.cf_api_token) {
        showDnsManager(result.cf_api_token);
    }
});

document.getElementById("btn-save-cf-token").addEventListener("click", () => {
    const token = cfTokenInput.value.trim();
    if (!token) return showToast("Insira o Token", "error");

    chrome.storage.local.set({ cf_api_token: token }, () => {
        showDnsManager(token);
        showToast("Token salvo!", "success");
    });
});

document.getElementById("btn-change-token").addEventListener("click", () => {
    chrome.storage.local.remove(["cf_api_token"], () => {
        cfTokenSection.style.display = "block";
        dnsManagerSection.style.display = "none";
        cfTokenInput.value = "";
    });
});

async function showDnsManager(token) {
    cfTokenSection.style.display = "none";
    dnsManagerSection.style.display = "block";

    // Auto-fill IP from connection tab if available
    const hostInput = document.getElementById("host");
    if (hostInput.value) {
        cfRecordContent.value = hostInput.value;
    }

    // Fetch Zones
    try {
        const res = await apiCall("/cloudflare/zones", "POST", { api_token: token });
        cfZoneSelect.innerHTML = `<option value="" disabled selected>Selecione uma Zona</option>`;

        if (res.zones && res.zones.length > 0) {
            res.zones.forEach(zone => {
                const opt = document.createElement("option");
                opt.value = zone.id;
                opt.textContent = zone.name;
                opt.dataset.name = zone.name;
                cfZoneSelect.appendChild(opt);
            });
        } else {
            cfZoneSelect.innerHTML = `<option value="" disabled>Nenhuma zona encontrada</option>`;
        }

    } catch (e) {
        showToast("Erro ao carregar zonas: " + e.message, "error");
        // Revert if invalid token
        document.getElementById("btn-change-token").click();
    }
}

// Update suffix hint when zone changes
cfZoneSelect.addEventListener("change", () => {
    const selectedOption = cfZoneSelect.options[cfZoneSelect.selectedIndex];
    if (selectedOption) {
        document.getElementById("cf-zone-suffix").textContent = "." + selectedOption.dataset.name;
        fetchDnsRecords(cfZoneSelect.value);
    }
});

async function fetchDnsRecords(zoneId) {
    const tokenResult = await new Promise(resolve => chrome.storage.local.get(["cf_api_token"], resolve));
    const token = tokenResult.cf_api_token;

    // IP Source of Truth only
    const hostInput = document.getElementById("host");
    const content = hostInput.value;

    if (!token || !zoneId || !content) return;

    const listContainer = document.getElementById("dns-records-list");
    const containerDiv = document.getElementById("dns-list-container");

    listContainer.innerHTML = "<p>Carregando...</p>";
    containerDiv.style.display = "block";

    try {
        const res = await apiCall("/cloudflare/records", "POST", {
            api_token: token,
            zone_id: zoneId,
            ip_filter: content
        });

        listContainer.innerHTML = "";

        if (res.records && res.records.length > 0) {
            res.records.forEach(record => {
                const item = document.createElement("div");
                item.style.cssText = "display: flex; justify-content: space-between; padding: 8px; background: rgba(255,255,255,0.05); margin-bottom: 5px; border-radius: 4px; align-items: center;";

                const proxiedIcon = record.proxied ? "☁️" : "🛡️";
                const proxiedTitle = record.proxied ? "Proxied (CDN)" : "DNS Only";

                item.innerHTML = `
                    <div style="flex: 1;">
                        <span style="display: block; font-weight: bold; color: var(--accent-color);">${record.name}</span>
                        <span style="font-size: 11px; color: #94a3b8;">${record.content}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span title="${proxiedTitle}" style="cursor: help;">${proxiedIcon}</span>
                        <button class="btn-icon-small btn-edit" title="Editar">✏️</button>
                        <button class="btn-icon-small btn-delete" title="Excluir">🗑️</button>
                    </div>
                `;

                // Add listeners
                const btnEdit = item.querySelector(".btn-edit");
                btnEdit.onclick = () => startEditMode(record);

                const btnDelete = item.querySelector(".btn-delete");
                btnDelete.onclick = () => {
                    console.log("Delete button clicked. Record data:", record);
                    console.log("Record ID:", record.id);
                    console.log("Record Name:", record.name);
                    deleteDnsRecord(record.id, record.name);
                };

                listContainer.appendChild(item);
            });
        } else {
            listContainer.innerHTML = "<p style='color: #94a3b8;'>Nenhum registro encontrado para este IP.</p>";
        }

    } catch (e) {
        listContainer.innerHTML = `<p style="color: #ef4444;">Erro: ${e.message}</p>`;
    }
}

// State for editing
let currentEditRecordId = null;

function startEditMode(record) {
    currentEditRecordId = record.id;

    // Extract subdomain from FQDN
    const zoneName = cfZoneSelect.options[cfZoneSelect.selectedIndex].dataset.name;
    let subdomain = record.name;
    if (subdomain.endsWith("." + zoneName)) {
        subdomain = subdomain.slice(0, -("." + zoneName).length);
    }
    // If it's the root domain (subdomain same as zone or empty), handle gracefully
    if (record.name === zoneName) subdomain = "@";

    document.getElementById("cf-record-name").value = subdomain;
    document.getElementById("cf-proxied").checked = record.proxied;

    const btnCreate = document.getElementById("btn-create-dns");
    btnCreate.textContent = "Atualizar Registro";

    document.getElementById("btn-cancel-edit-dns").style.display = "block";
    document.getElementById("cf-record-name").focus();
}

document.getElementById("btn-cancel-edit-dns").addEventListener("click", () => {
    resetEditMode();
});

function resetEditMode() {
    currentEditRecordId = null;
    document.getElementById("cf-record-name").value = "";
    document.getElementById("cf-proxied").checked = true;

    document.getElementById("btn-create-dns").textContent = "Criar Registro DNS";
    document.getElementById("btn-cancel-edit-dns").style.display = "none";
}

async function deleteDnsRecord(recordId, recordName) {
    if (!confirm(`Tem certeza que deseja excluir o registro ${recordName}?`)) return;

    const tokenResult = await new Promise(resolve => chrome.storage.local.get(["cf_api_token"], resolve));
    const token = tokenResult.cf_api_token;
    const zoneId = cfZoneSelect.value;

    try {
        await apiCall("/cloudflare/delete", "POST", {
            api_token: token,
            zone_id: zoneId,
            record_id: recordId
        });
        showToast("Registro excluído!", "success");
        fetchDnsRecords(zoneId); // Refresh

        if (currentEditRecordId === recordId) resetEditMode();

    } catch (e) {
        showToast("Erro ao excluir: " + e.message, "error");
    }
}

document.getElementById("btn-create-dns").addEventListener("click", () => {
    handleDnsAction();
});

async function handleDnsAction() {
    const tokenResult = await new Promise(resolve => chrome.storage.local.get(["cf_api_token"], resolve));
    const token = tokenResult.cf_api_token;

    if (!token) return showToast("Token não encontrado", "error");

    const zoneId = cfZoneSelect.value;
    const name = document.getElementById("cf-record-name").value;

    // IP Source of Truth from Connection Tab
    const hostInput = document.getElementById("host");
    const content = hostInput.value;

    const proxied = document.getElementById("cf-proxied").checked;

    if (!zoneId) return showToast("Selecione uma Zona", "error");
    if (!name) return showToast("Nome do registro é obrigatório", "error");
    if (!content) return showToast("Conecte-se ao servidor primeiro (IP ausente)", "error");

    const btnCreate = document.getElementById("btn-create-dns");
    const isUpdate = !!currentEditRecordId;

    btnCreate.textContent = isUpdate ? "Atualizando..." : "Criando...";
    btnCreate.disabled = true;

    try {
        if (isUpdate) {
            await apiCall("/cloudflare/update", "POST", {
                api_token: token,
                zone_id: zoneId,
                record_id: currentEditRecordId,
                name: name,
                content: content,
                proxied: proxied
            });
            showToast("DNS atualizado com sucesso!", "success");
            resetEditMode();
        } else {
            await apiCall("/cloudflare/create", "POST", {
                api_token: token,
                zone_id: zoneId,
                name: name,
                content: content,
                proxied: proxied
            });
            showToast("DNS criado com sucesso!", "success");
            document.getElementById("cf-record-name").value = "";
        }

        // Refresh list
        fetchDnsRecords(zoneId);

    } catch (e) {
        showToast(e.message, "error");
    } finally {
        if (!currentEditRecordId) btnCreate.textContent = "Criar Registro DNS";
        else btnCreate.textContent = "Atualizar Registro";
        btnCreate.disabled = false;
    }
}

// Initialization
document.addEventListener("DOMContentLoaded", () => {
    loadCredentialsFromStorage();
    // Disable all sidebar buttons except connection tab on load
    disableSidebarButtons();
});
