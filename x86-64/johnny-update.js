'use strict';
'require baseclass';
'require fs';
'require ui';
'require poll';

return baseclass.extend({
    load: function() {
        return fs.exec('/usr/libexec/johnny-update', ['status']);
    },
    action: function(action) {
        return fs.exec('/usr/libexec/johnny-update', [action]).then(function(res) {
            if (res.code !== 0) throw new Error(res.stderr || '更新操作失败');
        }).catch(function(e) {
            ui.addNotification(null, E('p', {}, e.message));
            throw e;
        });
    },
    render: function() {
        var self = this, readonly = !L.hasViewPermission();
        var current = E('span', {}, '读取中…'), latest = E('span', {}, '尚未检查'), message = E('p');
        var check = E('button', {'type': 'button', 'disabled': true, 'class': 'cbi-button cbi-button-action',
            'click': ui.createHandlerFn(this, 'action', 'check')}, '检查更新');
        var download = E('button', {'type': 'button', 'disabled': true, 'class': 'cbi-button cbi-button-action',
            'click': ui.createHandlerFn(this, 'action', 'download')}, '下载并校验');
        var flash = E('button', {'type': 'button', 'disabled': true, 'class': 'cbi-button cbi-button-apply', 'click': function() {
            ui.showModal('确认保留配置升级？', [
                E('p', {}, '升级会暂时中断网络并重启。请先下载配置备份；网络、MeowX 和 ZeroTier 配置将保留，自行安装的软件包可能需要重装。'),
                E('a', {'href': L.url('admin/system/flash'), 'target': '_blank', 'rel': 'noopener'}, '打开配置备份页面'),
                E('div', {'class': 'right'}, [
                    E('button', {'class': 'btn', 'click': ui.hideModal}, '取消'), ' ',
                    E('button', {'class': 'btn cbi-button-apply', 'click': ui.createHandlerFn(self, function() {
                        return self.action('flash').then(function() {
                            ui.showModal('正在升级', [E('p', {'class': 'spinning'}, '请勿断电，等待设备重新上线…')]);
                            ui.awaitReconnect(window.location.host);
                        });
                    })}, '确认升级并重启')
                ])
            ]);
        }}, '保留配置升级');
        function update(res) {
            if (res.code !== 0) throw new Error(res.stderr || '无法读取更新状态');
            var s = JSON.parse(res.stdout), busy = ['checking', 'downloading', 'flashing'].indexOf(s.state) >= 0;
            current.textContent = s.current;
            latest.textContent = s.latest || '尚未检查';
            message.textContent = s.message;
            message.className = busy ? 'spinning' : '';
            check.disabled = readonly || busy;
            download.disabled = readonly || s.state !== 'available';
            flash.disabled = readonly || s.state !== 'ready';
        }
        function refresh() {
            return self.load().then(update).catch(function(e) {
                message.textContent = '在线更新暂时不可用：' + e.message;
                check.disabled = download.disabled = flash.disabled = true;
            });
        }
        function row(title, content) {
            return E('div', {'class': 'cbi-value'}, [
                E('label', {'class': 'cbi-value-title'}, title),
                E('div', {'class': 'cbi-value-field'}, content)
            ]);
        }
        if (this.refreshPoll) poll.remove(this.refreshPoll);
        this.refreshPoll = refresh;
        poll.add(refresh, 3);
        return refresh().then(function() {
            return E('div', {'class': 'johnny-online-update'}, [
                E('h3', {}, '在线更新'),
                row('当前版本', current), row('最新版本', latest),
                row('更新来源', E('a', {'href': 'https://github.com/Johnnnnnnnyx/ImmortalWrt-ImageBuilder/releases',
                    'target': '_blank', 'rel': 'noopener'}, 'Johnnnnnnnyx / ImmortalWrt-ImageBuilder')),
                row('在线升级', [check, ' ', download, ' ', flash, message,
                    E('p', {'class': 'cbi-value-description'}, '下载并校验通过后，才可确认保留配置升级。')]),
                E('hr')
            ]);
        });
    }
});
