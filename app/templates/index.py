def get_html_template():
    return """
    <html>
        <head>
            <title>Auto Task System</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                .auth-container { max-width: 400px; margin: 50px auto; padding: 20px; background: #f8f9fa; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                .auth-form { display: none; }
                .auth-form.active { display: block; }
                .form-group { margin-bottom: 15px; }
                .form-group label { display: block; margin-bottom: 5px; }
                .form-group input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
                .auth-switch { text-align: center; margin-top: 15px; }
                .auth-switch a { color: #007bff; cursor: pointer; }
                .error-message { color: #dc3545; margin-top: 10px; }
                #status { padding: 10px; margin: 10px 0; border: 1px solid #ddd; }
                .task { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .progress-bar { height: 20px; background: #eee; border-radius: 10px; overflow: hidden; }
                .progress { height: 100%; background: #4CAF50; transition: width 0.3s ease; }
                #stats { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }
                #stats p { margin: 5px 0; }
                #rankings { background: #f8f9fa; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                .rank-item { display: flex; justify-content: space-between; padding: 10px; margin: 5px 0; background: white; border-radius: 4px; transition: transform 0.2s; }
                .rank-item:hover { transform: translateX(5px); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
                button { padding: 8px 16px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #0056b3; }
            </style>
        </head>
        <body>
            <div id="auth-container" class="auth-container">
                <div id="register-form" class="auth-form">
                    <h2>用户注册</h2>
                    <div class="form-group">
                        <label>用户名：</label>
                        <input type="text" id="username" placeholder="4-20位字母数字">
                    </div>
                    <button onclick="register()">立即注册</button>
                    <div class="auth-switch">
                        已有账号？<a onclick="showLogin()">立即登录</a>
                    </div>
                    <div id="register-error" class="error-message"></div>
                </div>

                <div id="login-form" class="auth-form">
                    <h2>系统登录</h2>
                    <div class="form-group">
                        <label>客户端ID：</label>
                        <input type="text" id="client-id" placeholder="输入您的客户端ID">
                    </div>
                    <button onclick="login()">立即登录</button>
                    <div class="auth-switch">
                        没有账号？<a onclick="showRegister()">立即注册</a>
                    </div>
                    <div id="login-error" class="error-message"></div>
                </div>
            </div>

            <div id="main-interface" style="display: none;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h1>Auto Task System</h1>
                    <div style="text-align: right;">
                        <p style="margin: 0;">用户名：<span id="user-name">-</span></p>
                        <p style="margin: 0; font-size: 0.8em; color: #666;">ID：<span id="user-client-id">-</span></p>
                    </div>
                </div>
                <div id="stats">
                    <p>Online Workers: <span id="online-count">0</span></p>
                    <p>Total Tasks: <span id="task-count">0</span></p>
                    <p>My Points: <span id="points">0</span></p>
                </div>
                <div id="current-task"></div>
                <div id="rankings">
                    <h2>Worker Rankings</h2>
                    <div id="rank-list"></div>
                </div>
            </div>

            <script>
                let ws = null;
                let currentTask = null;
                let clientId = localStorage.getItem('client_id');

                (function init() {
                    if (clientId) {
                        checkClientId(clientId).then(valid => {
                            if (valid) connectWebSocket(clientId);
                            else showLogin();
                        });
                    } else {
                        showRegister();
                    }
                })();

                function showRegister() {
                    document.getElementById('login-form').classList.remove('active');
                    document.getElementById('register-form').classList.add('active');
                }

                function showLogin() {
                    document.getElementById('register-form').classList.remove('active');
                    document.getElementById('login-form').classList.add('active');
                }

                async function register() {
                    const username = document.getElementById('username').value;
                    const errorElement = document.getElementById('register-error');
                        
                    if (!/^[a-zA-Z0-9]{4,20}$/.test(username)) {
                        errorElement.textContent = '用户名格式不正确（4-20位字母数字）';
                        return;
                    }

                    try {
                        const response = await fetch('/register', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ username })
                        });

                        if (!response.ok) {
                            const error = await response.json();
                            throw new Error(error.detail);
                        }

                        const data = await response.json();
                        localStorage.setItem('client_id', data.client_id);
                        connectWebSocket(data.client_id);
                    } catch (error) {
                        errorElement.textContent = error.message;
                    }
                }

                async function login() {
                    const clientId = document.getElementById('client-id').value;
                    const errorElement = document.getElementById('login-error');

                    try {
                        const valid = await checkClientId(clientId);
                        if (!valid) throw new Error('无效的客户端ID');
                        
                        localStorage.setItem('client_id', clientId);
                        connectWebSocket(clientId);
                    } catch (error) {
                        errorElement.textContent = error.message;
                    }
                }

                async function checkClientId(clientId) {
                    try {
                        const response = await fetch(`/user/${clientId}`);
                        return response.ok;
                    } catch {
                        return false;
                    }
                }

                function connectWebSocket(clientId) {
                    document.getElementById('auth-container').style.display = 'none';
                    document.getElementById('main-interface').style.display = 'block';
                    document.getElementById('user-client-id').textContent = clientId;

                    ws = new WebSocket(`ws://${location.host}/ws/${clientId}`);
                    
                    ws.onmessage = (event) => {
                        const msg = JSON.parse(event.data);
                        switch(msg.event) {
                            case 'init':
                                document.getElementById('online-count').textContent = msg.data.online_clients;
                                document.getElementById('task-count').textContent = msg.data.total_tasks;
                                document.getElementById('points').textContent = msg.data.points;
                                document.getElementById('user-name').textContent = msg.data.username || '-';
                                break;
                            case 'online_count':
                                document.getElementById('online-count').textContent = msg.data;
                                break;
                            case 'task_count':
                                document.getElementById('task-count').textContent = msg.data.total_tasks;
                                break;
                            case 'new_task':
                                showTask(msg.data);
                                currentTask = msg.data;
                                startAutoComplete(msg.data.duration);
                                break;
                            case 'points_update':
                                document.getElementById('points').textContent = msg.data.points;
                                break;
                            case 'waiting':
                                document.getElementById('current-task').innerHTML = 
                                    '<div class="task">Waiting for new tasks...</div>';
                                break;
                        }
                    };
                }

                function showTask(task) {
                    document.getElementById('current-task').innerHTML = `
                        <div class="task">
                            <h3>${task.name}</h3>
                            <p>Duration: ${task.duration}s</p>
                            <p>Reward: ${task.reward} points</p>
                            <div class="progress-bar">
                                <div class="progress" style="width: 0%"></div>
                            </div>
                        </div>
                    `;
                }

                function startAutoComplete(duration) {
                    const progressBar = document.querySelector('.progress');
                    let width = 0;
                    const interval = setInterval(() => {
                        width += 10 / duration;
                        progressBar.style.width = `${width}%`;
                        
                        if (width >= 100) {
                            clearInterval(interval);
                            ws.send(JSON.stringify({
                                event: "task_complete",
                                data: { task_id: currentTask.id, result: generateRandomHash() }
                            }));
                        }
                    }, 100);
                }
                
                function generateRandomHash() {
                    const array = new Uint8Array(16);
                    crypto.getRandomValues(array);
                    return Array.from(array, 
                        byte => byte.toString(16).padStart(2, '0')).join('');
                }
                        
                fetchRankings();
                setInterval(fetchRankings, 30000);

                async function fetchRankings() {
                    try {
                        const response = await fetch('/rank');
                        const rankings = await response.json();
                        renderRankings(rankings);
                    } catch (error) {
                        console.error('Failed to fetch rankings:', error);
                    }
                }

                function renderRankings(data) {
                    const container = document.getElementById('rank-list');
                    const items = data.map((item, index) => `
                        <div class="rank-item">
                            <div class="rank-position">#${index + 1}</div>
                            <div class="client-id">${item.username}</div>
                            <div class="points">${item.points} pts</div>
                        </div>
                    `).join('');
                    
                    container.innerHTML = `
                        <div style="margin-bottom: 10px; color: #666; font-size: 0.9em;">
                            Total Workers: ${data.length}
                        </div>
                        ${items}
                    `;
                }
            </script>
        </body>
    </html>
    """ 