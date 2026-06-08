// VeloGuard GNOME integration:
//   - VPN + Bulgarian Mode quick toggles (Quick Settings)
//   - a Fedora-style "Update VeloGuardOS on restart" checkbox injected into the
//     end-session (restart/shutdown) dialog when a kernel update is staged.
// Every action runs through bash (so PATH resolves) and fires a notification,
// so a press always gives visible feedback even if the underlying op no-ops.
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {QuickToggle, QuickMenuToggle, SystemIndicator}
    from 'resource:///org/gnome/shell/ui/quickSettings.js';
import * as EndSessionDialog from 'resource:///org/gnome/shell/ui/endSessionDialog.js';
import {CheckBox} from 'resource:///org/gnome/shell/ui/checkBox.js';

const PENDING = '/var/lib/veloguard/staged-kernel/pending.json';
// Arming writes /system-update (root); a polkit rule lets the active local user
// run this fixed wrapper without a password (see 49-veloguard-offline-update.rules).
const ARM = ['pkexec', '/usr/local/bin/veloguard-arm-offline-update'];

function run(cmd, note) {
    const full = `${cmd}; notify-send "VeloGuard" ${GLib.shell_quote(note)}`;
    try {
        GLib.spawn_command_line_async(`/bin/bash -lc ${GLib.shell_quote(full)}`);
    } catch (e) {
        logError(e, 'veloguard');
    }
}

const BgToggle = GObject.registerClass(
class BgToggle extends QuickToggle {
    _init() {
        super._init({title: 'Bulgarian Mode', iconName: 'folder-music-symbolic',
                     toggleMode: true});
        this.connect('clicked',
            () => run('veloguard-bulgarian-mode toggle', '🇧🇬 Bulgarian Mode toggled'));
    }
});

const VpnToggle = GObject.registerClass(
class VpnToggle extends QuickMenuToggle {
    _init() {
        super._init({title: 'VPN', iconName: 'network-vpn-symbolic',
                     toggleMode: true});
        this.menu.setHeader('network-vpn-symbolic', 'VeloGuard VPN');
        this.menu.addAction('Proton VPN', () => this._up('proton'));
        this.menu.addAction('Surfshark',  () => this._up('surfshark'));
        this.menu.addAction('NordVPN',    () => this._up('nord'));
        this.connect('clicked', () => {
            if (this.checked)
                run('pkexec wg-quick up veloguard', 'VPN connecting…');
            else
                run('pkexec wg-quick down veloguard', 'VPN off');
        });
    }
    _up(profile) {
        this.checked = true;
        run(`pkexec wg-quick up ${profile} 2>/dev/null || echo`,
            `VPN: ${profile} (import a config first if this didn't connect)`);
    }
});

const Indicator = GObject.registerClass(
class Indicator extends SystemIndicator {
    _init() {
        super._init();
        this._items = [new VpnToggle(), new BgToggle()];
        this._items.forEach(i => this.quickSettingsItems.push(i));
    }
});

// --- Fedora-style offline-update checkbox on the restart dialog -------------
// All of this is wrapped so a GNOME-version mismatch can never block restart:
// worst case the checkbox doesn't show and the dialog behaves normally.

function pendingVersion() {
    try {
        const [ok, bytes] = GLib.file_get_contents(PENDING);
        if (!ok) return null;
        return JSON.parse(new TextDecoder().decode(bytes)).version || null;
    } catch (_e) {
        return null;
    }
}

let _origOpen = null, _origConfirm = null;

function _ensureCheckbox(dlg) {
    const v = pendingVersion();
    const showable = dlg._type === 1 || dlg._type === 2;   // shutdown / restart
    if (!dlg._veloCheck) {
        if (!v || !showable) return;                       // nothing to offer
        dlg._veloCheck = new CheckBox('Update VeloGuardOS on restart');
        const box = dlg._messageDialogContent ?? dlg.contentLayout ?? null;
        if (box && box.add_child) box.add_child(dlg._veloCheck);
    }
    if (dlg._veloCheck) {
        dlg._veloCheck.visible = !!v && showable;
        const label = dlg._veloCheck.getLabelActor && dlg._veloCheck.getLabelActor();
        if (v && label) label.text = `Update VeloGuardOS (kernel ${v}) on restart`;
    }
}

function patchEndSession() {
    const proto = EndSessionDialog.EndSessionDialog && EndSessionDialog.EndSessionDialog.prototype;
    if (!proto) return;
    _origOpen = proto.open;
    proto.open = function (...args) {
        try { _ensureCheckbox(this); } catch (e) { logError(e, 'veloguard'); }
        return _origOpen.apply(this, args);
    };
    if (typeof proto._confirm === 'function') {
        _origConfirm = proto._confirm;
        proto._confirm = function (signal) {
            try {
                if (this._veloCheck && this._veloCheck.visible && this._veloCheck.checked) {
                    // spawn_sync: make sure /system-update is armed BEFORE the
                    // reboot proceeds (polkit lets the active user do it silently).
                    GLib.spawn_sync(null, ARM, null, GLib.SpawnFlags.SEARCH_PATH, null);
                }
            } catch (e) { logError(e, 'veloguard'); }
            return _origConfirm.call(this, signal);
        };
    }
}

function unpatchEndSession() {
    const proto = EndSessionDialog.EndSessionDialog && EndSessionDialog.EndSessionDialog.prototype;
    if (!proto) return;
    if (_origOpen) { proto.open = _origOpen; _origOpen = null; }
    if (_origConfirm) { proto._confirm = _origConfirm; _origConfirm = null; }
}

export default class VeloGuardToggles {
    enable() {
        this._indicator = new Indicator();
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);
        try { patchEndSession(); } catch (e) { logError(e, 'veloguard endSession'); }
    }
    disable() {
        try { unpatchEndSession(); } catch (e) { logError(e, 'veloguard'); }
        this._indicator?.quickSettingsItems.forEach(i => i.destroy());
        this._indicator?.destroy();
        this._indicator = null;
    }
}
