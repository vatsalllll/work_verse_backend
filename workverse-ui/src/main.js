import { Game } from './scenes/Game';
import { MainMenu } from './scenes/MainMenu';
import { Preloader } from './scenes/Preloader';
import { PauseMenu } from './scenes/PauseMenu';
import AuthService from './services/AuthService';
import { startHumanChat } from './humanChat';

const config = {
    type: Phaser.AUTO,
    width: 1024,
    height: 768,
    parent: 'game-container',
    scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH
    },
    scene: [
        Preloader,
        MainMenu,
        Game,
        PauseMenu
    ],
    physics: {
        default: "arcade",
        arcade: {
            gravity: { y: 0 },
        },
    },
};

let game = null;

function startGame() {
    const overlay = document.getElementById('auth-overlay');
    if (overlay) overlay.classList.add('hidden');
    if (!game) {
        game = new Phaser.Game(config);
    }
    showWhoami();
    startHumanChat();
}

function showWhoami() {
    const bar = document.getElementById('whoami');
    const nameEl = document.getElementById('whoami-name');
    const logoutBtn = document.getElementById('whoami-logout');
    const user = AuthService.getUser();
    nameEl.textContent = user ? `👤 ${user.name}` : '👤';
    bar.classList.remove('hc-hidden');
    logoutBtn.onclick = () => {
        AuthService.logout();
        window.location.reload();
    };
}

async function renderDemoUsers() {
    const wrap = document.getElementById('auth-demo');
    const list = document.getElementById('auth-demo-list');
    if (!wrap || !list) return;
    const users = await AuthService.getDemoUsers();
    if (!users.length) return;
    list.innerHTML = '';
    users.forEach((u) => {
        const btn = document.createElement('button');
        btn.className = 'demo-btn';
        btn.textContent = `Log in as ${u.name}`;
        btn.addEventListener('click', async () => {
            try {
                await AuthService.demoLogin(u.email);
                startGame();
            } catch (e) {
                document.getElementById('auth-error').textContent =
                    'Demo login failed: ' + (e.message || '');
            }
        });
        list.appendChild(btn);
    });
    wrap.classList.remove('hc-hidden');
}

function setupAuthUI() {
    const overlay = document.getElementById('auth-overlay');
    const nameInput = document.getElementById('auth-name');
    const emailInput = document.getElementById('auth-email');
    const passwordInput = document.getElementById('auth-password');
    const submitBtn = document.getElementById('auth-submit');
    const errorBox = document.getElementById('auth-error');
    const subtitle = document.getElementById('auth-subtitle');
    const toggleLink = document.getElementById('auth-toggle-link');
    const toggleText = document.getElementById('auth-toggle');
    const googleBtn = document.getElementById('auth-google');
    const slackBtn = document.getElementById('auth-slack');

    let mode = 'login'; // 'login' | 'signup'

    const setMode = (newMode) => {
        mode = newMode;
        errorBox.textContent = '';
        if (mode === 'signup') {
            nameInput.style.display = 'block';
            submitBtn.textContent = 'Sign Up';
            subtitle.textContent = 'Create your WorkVerse account';
            toggleText.innerHTML = 'Already have an account? <a id="auth-toggle-link">Log in</a>';
        } else {
            nameInput.style.display = 'none';
            submitBtn.textContent = 'Log In';
            subtitle.textContent = 'Log in to enter the virtual office';
            toggleText.innerHTML = "No account? <a id=\"auth-toggle-link\">Sign up</a>";
        }
        // Re-bind toggle link (innerHTML replaced the element)
        document.getElementById('auth-toggle-link')
            .addEventListener('click', () => setMode(mode === 'login' ? 'signup' : 'login'));
    };

    const submit = async () => {
        const email = emailInput.value.trim();
        const password = passwordInput.value;
        const name = nameInput.value.trim();
        errorBox.textContent = '';

        if (!email || !password || (mode === 'signup' && !name)) {
            errorBox.textContent = 'Please fill in all fields.';
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = mode === 'signup' ? 'Creating…' : 'Logging in…';
        try {
            if (mode === 'signup') {
                await AuthService.register(name, email, password);
            } else {
                await AuthService.login(email, password);
            }
            startGame();
        } catch (err) {
            errorBox.textContent = err.message || 'Something went wrong.';
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = mode === 'signup' ? 'Sign Up' : 'Log In';
        }
    };

    submitBtn.addEventListener('click', submit);
    passwordInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    toggleLink.addEventListener('click', () => setMode('signup'));

    // OAuth buttons — navigate to the backend, which redirects to the provider.
    googleBtn.addEventListener('click', () => AuthService.oauthLogin('google'));
    slackBtn.addEventListener('click', () => AuthService.oauthLogin('slack'));

    // Surface any error returned by an OAuth redirect (?auth_error=...).
    const authError = new URLSearchParams(window.location.search).get('auth_error');
    if (authError) {
        const messages = {
            google_not_configured: 'Google sign-in is not set up yet on the server.',
            slack_not_configured: 'Slack sign-in is not set up yet on the server.',
            google_login_failed: 'Google sign-in failed. Please try again.',
            slack_login_failed: 'Slack sign-in failed. Please try again.',
            invalid_state: 'Sign-in expired. Please try again.'
        };
        errorBox.textContent = messages[authError] || 'Sign-in failed. Please try again.';
        window.history.replaceState({}, document.title, window.location.pathname);
    }
}

async function init() {
    setupAuthUI();
    // If we already have a (valid) token, skip the login screen.
    if (AuthService.isLoggedIn() && await AuthService.verifyToken()) {
        startGame();
        return;
    }
    renderDemoUsers();
}

if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
