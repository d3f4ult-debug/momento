import 'package:flutter/material.dart';
import '../models/window_target.dart';
import '../services/bridge_service.dart';
import '../theme/app_theme.dart';

class TargetPickerDropZone extends StatefulWidget {
  final BridgeService bridgeService;
  final void Function(WindowTarget target)? onWindowSelected;
  final void Function(Map<String, dynamic> metadata)? onTargetResolved;
  final void Function(WindowTarget target)? onDirectProfileRequested;

  const TargetPickerDropZone({
    super.key,
    required this.bridgeService,
    this.onWindowSelected,
    this.onTargetResolved,
    this.onDirectProfileRequested,
  });

  @override
  State<TargetPickerDropZone> createState() => _TargetPickerDropZoneState();
}

class _TargetPickerDropZoneState extends State<TargetPickerDropZone> {
  final _pathInputController = TextEditingController();
  bool _isResolving = false;
  String? _statusMessage;
  WindowTarget? _selectedWindow;

  @override
  void dispose() {
    _pathInputController.dispose();
    super.dispose();
  }

  Future<void> _handlePathSubmitted(String rawPath) async {
    final clean = rawPath.trim();
    if (clean.isEmpty) return;

    setState(() {
      _isResolving = true;
      _statusMessage = null;
    });

    try {
      final res = await widget.bridgeService.resolveTarget(clean);
      if (mounted) {
        if (res['success'] == true) {
          final binPath = res['binary_path']?.toString() ?? clean;
          final appName = res['name']?.toString() ?? '';
          final pid = res['pid'] is int ? res['pid'] as int : null;
          setState(() {
            _statusMessage = 'Resolved "$appName" (${res['exists'] == true ? 'Binary verified' : 'Path accepted'})';
            if (pid != null && pid > 0) {
              _statusMessage = '$_statusMessage • Running (PID: $pid)';
            }
          });
          widget.onTargetResolved?.call(res);
        } else {
          setState(() {
            _statusMessage = res['error']?.toString() ?? 'Could not resolve path.';
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _statusMessage = 'Error resolving target: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() => _isResolving = false);
      }
    }
  }

  Future<void> _openWindowPickerModal() async {
    setState(() {
      _isResolving = true;
      _statusMessage = 'Scanning desktop windows...';
    });

    try {
      final rawWindows = await widget.bridgeService.listWindows();
      if (!mounted) return;
      setState(() => _isResolving = false);

      final windows = rawWindows
          .map((w) => WindowTarget.fromJson(w))
          .where((w) =>
              w.title.trim().isNotEmpty &&
              !['Program Manager', 'Task Switching', 'Taskbar'].contains(w.title.trim()))
          .toList();

      if (windows.isEmpty) {
        setState(() => _statusMessage = 'No active application windows found.');
        return;
      }

      final chosen = await showDialog<WindowTarget>(
        context: context,
        builder: (ctx) => _WindowSelectionDialog(windows: windows),
      );

      if (chosen != null && mounted) {
        setState(() {
          _selectedWindow = chosen;
          _statusMessage = 'Target bound: "${chosen.title}" (PID: ${chosen.pid})';
          _pathInputController.text = chosen.processPath.isNotEmpty ? chosen.processPath : chosen.title;
        });

        widget.onWindowSelected?.call(chosen);

        // Also pass as resolved target metadata
        widget.onTargetResolved?.call({
          'success': true,
          'name': chosen.title,
          'binary_path': chosen.processPath,
          'working_dir': chosen.workingDir,
          'arguments': '',
          'exists': chosen.processPath.isNotEmpty,
          'pid': chosen.pid,
          'handle': chosen.handle,
          'window_title': chosen.title,
          'process_name': chosen.processName,
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isResolving = false;
          _statusMessage = 'Error listing windows: $e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.bgDark.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: _selectedWindow != null ? AppTheme.accent : AppTheme.borderColor,
          width: _selectedWindow != null ? 1.5 : 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.gps_fixed_rounded, color: AppTheme.accent, size: 16),
              const SizedBox(width: 8),
              const Text(
                'Visual Target Picker & Drop Zone',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: AppTheme.textMain,
                ),
              ),
              const Spacer(),
              if (_selectedWindow != null && widget.onDirectProfileRequested != null)
                TextButton.icon(
                  onPressed: () => widget.onDirectProfileRequested!(_selectedWindow!),
                  icon: const Icon(Icons.flash_on, size: 13, color: Color(0xFF10B981)),
                  label: const Text(
                    'Profile Window Now',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFF10B981)),
                  ),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    visualDensity: VisualDensity.compact,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            'Drop or paste a shortcut (.lnk), executable (.exe), or click "Pick Window" to visually target any open desktop window.',
            style: TextStyle(fontSize: 11, color: AppTheme.textMuted),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _pathInputController,
                  style: const TextStyle(fontSize: 12, color: AppTheme.textMain),
                  decoration: InputDecoration(
                    hintText: 'Drop or paste path (e.g. C:\\Games\\Dokonchi.lnk or .exe)',
                    hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 11),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    filled: true,
                    fillColor: AppTheme.bgCard,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(6),
                      borderSide: const BorderSide(color: AppTheme.borderColor),
                    ),
                    suffixIcon: _isResolving
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: Padding(
                              padding: EdgeInsets.all(10.0),
                              child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.accent),
                            ),
                          )
                        : IconButton(
                            icon: const Icon(Icons.arrow_forward, size: 14, color: AppTheme.accent),
                            tooltip: 'Resolve dropped or typed path',
                            onPressed: () => _handlePathSubmitted(_pathInputController.text),
                          ),
                  ),
                  onSubmitted: _handlePathSubmitted,
                ),
              ),
              const SizedBox(width: 8),
              ElevatedButton.icon(
                onPressed: _isResolving ? null : _openWindowPickerModal,
                icon: const Icon(Icons.filter_center_focus, size: 14),
                label: const Text('Pick Window', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.accent.withValues(alpha: 0.2),
                  foregroundColor: AppTheme.accent,
                  elevation: 0,
                  side: const BorderSide(color: AppTheme.accent),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                ),
              ),
            ],
          ),
          if (_statusMessage != null) ...[
            const SizedBox(height: 6),
            Row(
              children: [
                Icon(
                  _selectedWindow != null ? Icons.check_circle_outline : Icons.info_outline,
                  size: 13,
                  color: _selectedWindow != null ? const Color(0xFF10B981) : AppTheme.textMuted,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    _statusMessage!,
                    style: TextStyle(
                      fontSize: 11,
                      color: _selectedWindow != null ? const Color(0xFF10B981) : AppTheme.textMuted,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _WindowSelectionDialog extends StatefulWidget {
  final List<WindowTarget> windows;

  const _WindowSelectionDialog({required this.windows});

  @override
  State<_WindowSelectionDialog> createState() => _WindowSelectionDialogState();
}

class _WindowSelectionDialogState extends State<_WindowSelectionDialog> {
  String _filter = '';

  @override
  Widget build(BuildContext context) {
    final filtered = widget.windows.where((w) {
      final q = _filter.toLowerCase();
      return w.title.toLowerCase().contains(q) ||
          w.processName.toLowerCase().contains(q) ||
          w.pid.toString().contains(q);
    }).toList();

    return AlertDialog(
      backgroundColor: AppTheme.bgSurface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: AppTheme.borderColor),
      ),
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.filter_center_focus, color: AppTheme.accent, size: 20),
              const SizedBox(width: 8),
              const Text(
                'Select Active Target Window',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.textMain),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppTheme.accent.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  '${widget.windows.length} Running',
                  style: const TextStyle(fontSize: 11, color: AppTheme.accent, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'Target an open process or app window directly to inspect or profile its UI tree.',
            style: TextStyle(fontSize: 11, color: AppTheme.textMuted),
          ),
          const SizedBox(height: 12),
          TextField(
            autofocus: true,
            style: const TextStyle(fontSize: 12, color: AppTheme.textMain),
            decoration: InputDecoration(
              hintText: 'Filter windows by name, process, or PID...',
              hintStyle: const TextStyle(fontSize: 11, color: AppTheme.textMuted),
              prefixIcon: const Icon(Icons.search, size: 14, color: AppTheme.textMuted),
              contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              filled: true,
              fillColor: AppTheme.bgDark,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(6),
                borderSide: const BorderSide(color: AppTheme.borderColor),
              ),
            ),
            onChanged: (val) => setState(() => _filter = val),
          ),
        ],
      ),
      content: SizedBox(
        width: 480,
        height: 320,
        child: filtered.isEmpty
            ? const Center(
                child: Text('No matching windows found.', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
              )
            : ListView.separated(
                itemCount: filtered.length,
                separatorBuilder: (_, __) => const Divider(color: AppTheme.borderColor, height: 1),
                itemBuilder: (context, idx) {
                  final win = filtered[idx];
                  return ListTile(
                    dense: true,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    leading: Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: AppTheme.bgDark,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: AppTheme.borderColor),
                      ),
                      child: const Icon(Icons.desktop_windows_outlined, size: 16, color: AppTheme.accent),
                    ),
                    title: Text(
                      win.title,
                      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    subtitle: Text(
                      'PID: ${win.pid} • ${win.processName.isNotEmpty ? win.processName : "Process"} • ${win.processPath.isNotEmpty ? win.processPath : "Native Handle 0x${win.handle.toRadixString(16)}"}',
                      style: const TextStyle(fontSize: 10, color: AppTheme.textMuted),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: const Icon(Icons.arrow_forward_ios, size: 11, color: AppTheme.textMuted),
                    onTap: () => Navigator.pop(context, win),
                  );
                },
              ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
        ),
      ],
    );
  }
}
