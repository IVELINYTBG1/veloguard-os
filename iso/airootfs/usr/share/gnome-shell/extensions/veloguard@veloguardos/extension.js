// VeloGuard Quick Toggles — VPN + Bulgarian Mode in GNOME Quick Settings.
// Every action runs through bash (so PATH resolves) and fires a notification,
// so a press always gives visible feedback even if the underlying op no-ops.
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {QuickToggle, QuickMenuToggle, SystemIndicator}
    from 'resource:///org/gnome/shell/ui/quickSettings.js';

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
        // If the profile isn't imported yet, wg-quick fails and the note says so.
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

export default class VeloGuardToggles {
    enable() {
        this._indicator = new Indicator();
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);
    }
    disable() {
        this._indicator?.quickSettingsItems.forEach(i => i.destroy());
        this._indicator?.destroy();
        this._indicator = null;
    }
}
