import 'package:flutter/material.dart';
import '../services/bridge_service.dart';
import '../theme/app_theme.dart';
import 'target_picker_drop_zone.dart';

class RegisterAppDialog extends StatefulWidget {
  final BridgeService bridgeService;
  final Future<bool> Function(
    String name,
    String binaryPath,
    List<String> aliases,
    String category,
    String? workingDir,
    String? arguments,
  ) onRegister;

  const RegisterAppDialog({
    super.key,
    required this.bridgeService,
    required this.onRegister,
  });

  @override
  State<RegisterAppDialog> createState() => _RegisterAppDialogState();
}

class _RegisterAppDialogState extends State<RegisterAppDialog> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _pathController = TextEditingController();
  final _aliasesController = TextEditingController();
  final _workingDirController = TextEditingController();
  final _argumentsController = TextEditingController();
  String _category = 'custom';
  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void dispose() {
    _nameController.dispose();
    _pathController.dispose();
    _aliasesController.dispose();
    _workingDirController.dispose();
    _argumentsController.dispose();
    super.dispose();
  }

  void _onTargetAutoFilled(Map<String, dynamic> meta) {
    setState(() {
      if (meta['name'] != null && meta['name'].toString().isNotEmpty) {
        _nameController.text = meta['name'].toString();
      }
      if (meta['binary_path'] != null && meta['binary_path'].toString().isNotEmpty) {
        _pathController.text = meta['binary_path'].toString();
      }
      if (meta['working_dir'] != null && meta['working_dir'].toString().isNotEmpty) {
        _workingDirController.text = meta['working_dir'].toString();
      }
      if (meta['arguments'] != null && meta['arguments'].toString().isNotEmpty) {
        _argumentsController.text = meta['arguments'].toString();
      }
    });
  }

  Future<void> _handleSubmit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    final name = _nameController.text.trim();
    final path = _pathController.text.trim();
    final rawAliases = _aliasesController.text
        .split(',')
        .map((a) => a.trim())
        .where((a) => a.isNotEmpty)
        .toList();
    final workingDir = _workingDirController.text.trim();
    final arguments = _argumentsController.text.trim();

    try {
      final success = await widget.onRegister(
        name,
        path,
        rawAliases,
        _category,
        workingDir.isEmpty ? null : workingDir,
        arguments.isEmpty ? null : arguments,
      );
      if (mounted) {
        if (success) {
          Navigator.of(context).pop(true);
        } else {
          setState(() {
            _errorMessage = 'Failed to register application. Check executable path.';
            _isSubmitting = false;
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Error: $e';
          _isSubmitting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 500,
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.9,
        ),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: AppTheme.bgSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppTheme.borderColor),
        ),
        child: SingleChildScrollView(
          child: Form(
            key: _formKey,
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
                      child: const Icon(Icons.app_registration, color: AppTheme.accent, size: 20),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Teach Momento App',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              color: AppTheme.textMain,
                            ),
                          ),
                          Text(
                            'Register custom binary or application manually',
                            style: TextStyle(fontSize: 12, color: AppTheme.textMuted),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),

                TargetPickerDropZone(
                  bridgeService: widget.bridgeService,
                  onTargetResolved: _onTargetAutoFilled,
                  onWindowSelected: (win) {
                    _onTargetAutoFilled({
                      'name': win.title,
                      'binary_path': win.processPath,
                      'working_dir': win.workingDir,
                    });
                  },
                ),
                const SizedBox(height: 16),

                if (_errorMessage != null) ...[
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: AppTheme.danger.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: AppTheme.danger.withValues(alpha: 0.3)),
                    ),
                    child: Text(
                      _errorMessage!,
                      style: const TextStyle(color: AppTheme.danger, fontSize: 12),
                    ),
                  ),
                  const SizedBox(height: 12),
                ],

                const Text('Application Name *', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                const SizedBox(height: 6),
                TextFormField(
                  controller: _nameController,
                  style: const TextStyle(fontSize: 13),
                  decoration: const InputDecoration(
                    hintText: 'e.g. Notepad++, Blender, CustomTool',
                  ),
                  validator: (val) => val == null || val.trim().isEmpty ? 'Please enter an app name' : null,
                ),
                const SizedBox(height: 14),

                const Text('Executable / Binary Path *', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                const SizedBox(height: 6),
                TextFormField(
                  controller: _pathController,
                  style: const TextStyle(fontSize: 13),
                  decoration: const InputDecoration(
                    hintText: r'e.g. C:\Program Files\Notepad++\notepad++.exe or shortcut (.lnk)',
                  ),
                  validator: (val) => val == null || val.trim().isEmpty ? 'Please enter binary path' : null,
                ),
                const SizedBox(height: 14),

                const Text('Working Directory (Optional)', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                const SizedBox(height: 6),
                TextFormField(
                  controller: _workingDirController,
                  style: const TextStyle(fontSize: 13),
                  decoration: const InputDecoration(
                    hintText: r'e.g. C:\Program Files\App (defaults to executable folder)',
                  ),
                ),
                const SizedBox(height: 14),

                const Text('Arguments / Data File Path (Optional)', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                const SizedBox(height: 6),
                TextFormField(
                  controller: _argumentsController,
                  style: const TextStyle(fontSize: 13),
                  decoration: const InputDecoration(
                    hintText: r'e.g. --config app.json or C:\data\database.db',
                  ),
                ),
                const SizedBox(height: 14),

                const Text('Search Aliases (Optional, comma-separated)', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                const SizedBox(height: 6),
                TextFormField(
                  controller: _aliasesController,
                  style: const TextStyle(fontSize: 13),
                  decoration: const InputDecoration(
                    hintText: 'e.g. npp, editor, code',
                  ),
                ),
                const SizedBox(height: 14),

                const Text('Category', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                const SizedBox(height: 6),
                DropdownButtonFormField<String>(
                  initialValue: _category,
                  dropdownColor: AppTheme.bgCard,
                  style: const TextStyle(fontSize: 13, color: AppTheme.textMain),
                  decoration: const InputDecoration(),
                  items: const [
                    DropdownMenuItem(value: 'custom', child: Text('Custom Application')),
                    DropdownMenuItem(value: 'utility', child: Text('Utility & Tools')),
                    DropdownMenuItem(value: 'development', child: Text('Development & IDE')),
                    DropdownMenuItem(value: 'graphics', child: Text('Graphics & Media')),
                    DropdownMenuItem(value: 'internet', child: Text('Internet & Browser')),
                  ],
                  onChanged: (val) {
                    if (val != null) setState(() => _category = val);
                  },
                ),
                const SizedBox(height: 24),

              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: _isSubmitting ? null : () => Navigator.of(context).pop(false),
                    child: const Text('Cancel', style: TextStyle(color: AppTheme.textMuted)),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: _isSubmitting ? null : _handleSubmit,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.accent,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                    ),
                    child: _isSubmitting
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Text('Register App', style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
}
