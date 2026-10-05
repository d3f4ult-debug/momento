import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class OnboardingDialog extends StatefulWidget {
  final String initialBackendUrl;
  final Future<void> Function(String backendUrl) onComplete;

  const OnboardingDialog({
    super.key,
    required this.initialBackendUrl,
    required this.onComplete,
  });

  @override
  State<OnboardingDialog> createState() => _OnboardingDialogState();
}

class _OnboardingDialogState extends State<OnboardingDialog> {
  late final TextEditingController _urlController;
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: widget.initialBackendUrl);
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _handleConfirm() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      await widget.onComplete(_urlController.text.trim());
      if (mounted) {
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
      child: Container(
        width: 520,
        padding: const EdgeInsets.all(28),
        decoration: BoxDecoration(
          color: AppTheme.bgSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppTheme.borderColor),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.6),
              blurRadius: 30,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppTheme.accent.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(Icons.security, color: AppTheme.accentLight, size: 22),
                ),
                const SizedBox(width: 12),
                const Text(
                  'Welcome to Momento Desktop',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              'To launch, monitor, and automate applications on your laptop or inside isolated VPS sandboxes, Momento requests initial local permissions.',
              style: TextStyle(fontSize: 13, height: 1.45, color: AppTheme.textMuted),
            ),
            const SizedBox(height: 18),

            // Permission 1
            _buildPermissionItem(
              icon: Icons.folder_open,
              title: 'System File Indexing',
              desc: 'Scan common Windows program paths, Start Menu, and PATH directories.',
            ),
            const SizedBox(height: 10),

            // Permission 2
            _buildPermissionItem(
              icon: Icons.inventory_2_outlined,
              title: 'App Registry Discovery',
              desc: 'Catalog installed local applications into a searchable registry file.',
            ),
            const SizedBox(height: 10),

            // Permission 3
            _buildPermissionItem(
              icon: Icons.play_arrow_outlined,
              title: 'Execution Management',
              desc: 'Spawn, inspect, and monitor processes natively or on Contabo VPS.',
            ),
            const SizedBox(height: 18),

            // Backend URL Config
            const Text(
              'Momento VPS Backend API',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppTheme.textMuted),
            ),
            const SizedBox(height: 6),
            TextField(
              controller: _urlController,
              style: const TextStyle(fontSize: 13),
              decoration: const InputDecoration(
                hintText: 'http://161.97.64.38:8000',
              ),
            ),
            if (_errorMessage != null) ...[
              const SizedBox(height: 10),
              Text(_errorMessage!, style: const TextStyle(color: AppTheme.danger, fontSize: 12)),
            ],
            const SizedBox(height: 24),

            // Actions
            Align(
              alignment: Alignment.centerRight,
              child: ElevatedButton(
                onPressed: _isLoading ? null : _handleConfirm,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.accent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                ),
                child: _isLoading
                    ? const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          ),
                          SizedBox(width: 10),
                          Text('Scanning Applications...', style: TextStyle(fontSize: 13)),
                        ],
                      )
                    : const Text(
                        'Grant Permissions & Scan Apps',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPermissionItem({
    required IconData icon,
    required String title,
    required String desc,
  }) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppTheme.bgCard,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.borderColor.withValues(alpha: 0.6)),
      ),
      child: Row(
        children: [
          const Icon(Icons.check_circle, color: AppTheme.success, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.textMain)),
                Text(desc, style: const TextStyle(fontSize: 11, color: AppTheme.textMuted)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
