'use strict';
'require view';
'require fs';
'require ui';
'require poll';

return view.extend({
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
    render: function(initial) {
        var self = this, readonly = !L.hasViewPermission();
        var info = E('div'), check = E('button', {'class': 'cbi-button cbi-button-action',
            'click': ui.createHandlerFn(this, 'action', 'check')}, '检查更新');
        var download = E('button', {'class': 'cbi-button cbi-button-action',
            'click': ui.createHandlerFn(this, 'action', 'download')}, '下载并校验');
        var flash = E('button', {'class': 'cbi-button cbi-button-apply', 'click': function() {
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
            info.replaceChildren(E('p', {}, '当前版本：' + s.current),
                E('p', {}, '仓库版本：' + (s.latest || '尚未检查')),
                E('p', {'class': busy ? 'spinning' : ''}, s.message));
            check.disabled = readonly || busy;
            download.disabled = readonly || s.state !== 'available';
            flash.disabled = readonly || s.state !== 'ready';
        }
        update(initial);
        poll.add(function() {
            return self.load().then(update).catch(function(e) {
                info.replaceChildren(E('p', {}, e.message));
                check.disabled = download.disabled = flash.disabled = true;
            });
        }, 3);
        return E('div', {'class': 'cbi-map'}, [
            E('h2', {}, 'Johnnywrt 在线更新'),
            E('p', {}, '检查兼容的 x86-64 UEFI 稳定固件。下载校验后由你确认升级。'),
            E('a', {'href': 'https://github.com/Johnnnnnnnyx/ImmortalWrt-ImageBuilder/releases',
                'target': '_blank', 'rel': 'noopener'}, '查看固件发布与更新说明'),
            info, E('div', {}, [check, ' ', download, ' ', flash])
        ]);
    },
    handleSaveApply: null,
    handleSave: null,
    handleReset: null
});
