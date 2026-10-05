import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../theme/app_theme.dart';

class SettingsDialog extends StatefulWidget {
  final String currentUrl;
  final String currentMode;
  final Function(String newUrl, String newMode) onSave;

  const SettingsDialog({
    super.key,
    required this.currentUrl,
    required this.currentMode,
    required this.onSave,
  });

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  late final TextEditingController _urlController;
  late String _selectedMode;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: widget.currentUrl);
    _selectedMode = widget.currentMode;
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 460,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: AppTheme.bgSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppTheme.borderColor),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Momento Configuration',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.textMain),
            ),
            const SizedBox(height: 16),
            const Text('Backend API URL', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
            const SizedBox(height: 6),
            TextField(
              controller: _urlController,
              style: const TextStyle(fontSize: 13),
              decoration: const InputDecoration(hintText: AppConfig.defaultVpsUrl),
            ),
            const SizedBox(height: 16),
            const Text('Execution Target Mode', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
            const SizedBox(height: 6),
            DropdownButtonFormField<String>(
              initialValue: _selectedMode,
              dropdownColor: AppTheme.bgCard,
              style: const TextStyle(fontSize: 13, color: AppTheme.textMain),
              decoration: const InputDecoration(),
              items: const [
                DropdownMenuItem(value: AppConfig.modeHybrid, child: Text('Hybrid Auto (Recommended)')),
                DropdownMenuItem(value: AppConfig.modeLocal, child: Text('Local Host (Windows Native)')),
                DropdownMenuItem(value: AppConfig.modeVps, child: Text('VPS Sandbox (Contabo Isolated)')),
              ],
              onChanged: (val) {
                if (val != null) setState(() => _selectedMode = val);
              },
            ),
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Cancel', style: TextStyle(color: AppTheme.textMuted)),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: () {
                    widget.onSave(_urlController.text.trim(), _selectedMode);
                    Navigator.of(context).pop();
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.accent,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                  ),
                  child: const Text('Save Settings', style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
