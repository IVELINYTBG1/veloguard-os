// VeloGuard Quick Toggles — adds VPN + Bulgarian Mode to GNOME Quick Settings.
// (Quick Settings orders its own toggles; these appear in the panel grid.)
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {QuickToggle, QuickMenuToggle, SystemIndicator}
    from 'resource:///org/gnome/shell/ui/quickSettings.js';

function run(cmd) { try { GLib.spawn_command_line_async(cmd); } catch (e) {} }

const BgToggle = GObject.registerClass(
class BgToggle extends QuickToggle {
    _init() {
        super._init({title: 'Bulgarian Mode', iconName: 'folder-music-symbolic',
                     toggleMode: true});
        this.connect('clicked', () => run('veloguard-bulgarian-mode toggle'));
    }
});

const VpnToggle = GObject.registerClass(
class VpnToggle extends QuickMenuToggle {
    _init() {
        super._init({title: 'VPN', iconName: 'network-vpn-symbolic',
                     toggleMode: true});
        this.menu.setHeader('network-vpn-symbolic', 'VeloGuard VPN');
        // Each provider is an imported WireGuard profile (veloguard-vpn import).
        this.menu.addAction('Proton VPN', () => this._up('proton'));
        this.menu.addAction('Surfshark',  () => this._up('surfshark'));
        this.menu.addAction('NordVPN',    () => this._up('nord'));
        this.connect('clicked', () => {
            if (this.checked) this._up('veloguard');
            else run('pkexec wg-quick down veloguard');
        });
    }
    _up(profile) {
        this.checked = true;
        run(`pkexec wg-quick up ${profile}`);
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
