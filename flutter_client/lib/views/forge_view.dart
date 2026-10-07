import 'package:flutter/material.dart';
import '../services/bridge_service.dart';
import '../theme/app_theme.dart';

class ForgeView extends StatefulWidget {
  final BridgeService bridgeService;

  const ForgeView({super.key, required this.bridgeService});

  @override
  State<ForgeView> createState() => _ForgeViewState();
}

class _ForgeViewState extends State<ForgeView> {
  final _nameController = TextEditingController();
  final _descController = TextEditingController();
  String _category = 'retail';
  bool _isBuilding = false;
  List<Map<String, dynamic>> _apps = [];
  Map<String, dynamic>? _selectedApp;
  String? _statusMessage;

  final List<String> _categories = ['retail', 'inventory', 'crm', 'finance', 'logistics', 'utility'];

  @override
  void initState() {
    super.initState();
    _loadApps();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _descController.dispose();
    super.dispose();
  }

  Future<void> _loadApps() async {
    final list = await widget.bridgeService.listForgeApps();
    if (mounted) {
      setState(() {
        _apps = list;
        if (_selectedApp == null && list.isNotEmpty) {
          _selectedApp = list.first;
        }
      });
    }
  }

  Future<void> _handleBuildApp() async {
    final name = _nameController.text.trim();
    if (name.isEmpty || _isBuilding) return;

    setState(() {
      _isBuilding = true;
      _statusMessage = null;
    });

    try {
      final res = await widget.bridgeService.buildForgeApp(
        name,
        category: _category,
        description: _descController.text.trim(),
      );
      if (mounted) {
        if (res['success'] == true) {
          final app = res['app'] as Map<String, dynamic>?;
          setState(() {
            _selectedApp = app;
            _statusMessage = res['message']?.toString() ?? 'App created with zero-vision control.';
            _nameController.clear();
            _descController.clear();
          });
          _loadApps();
        } else {
          setState(() => _statusMessage = res['error']?.toString() ?? 'Build failed.');
        }
      }
    } catch (e) {
      if (mounted) setState(() => _statusMessage = 'Build error: $e');
    } finally {
      if (mounted) setState(() => _isBuilding = false);
    }
  }

  Future<void> _executeHook(String action, [Map<String, dynamic>? payload]) async {
    if (_selectedApp == null) return;
    final appId = _selectedApp!['id'].toString();

    setState(() => _statusMessage = 'Executing zero-vision hook "$action"...');

    try {
      final res = await widget.bridgeService.executeForgeHook(appId, action, payload: payload);
      if (mounted) {
        setState(() {
          _statusMessage = res['log']?.toString() ?? 'Zero-vision action completed.';
        });
        _loadApps();
      }
    } catch (e) {
      if (mounted) setState(() => _statusMessage = 'Hook error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppTheme.bgDark,
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [Color(0xFFF59E0B), Color(0xFFEF4444)]),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.handyman, color: Colors.white, size: 22),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Forge — App Builder & Zero-Vision Native Control',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      'Generate custom business software with internal control hooks. Maestro controls them without slow vision models.',
                      style: TextStyle(fontSize: 12, color: AppTheme.textMuted),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.refresh, size: 18, color: AppTheme.textMuted),
                tooltip: 'Refresh Apps',
                onPressed: _loadApps,
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Main Workspace
          Expanded(
            child: Row(
              children: [
                // Left: App Creator & App Selector
                Expanded(
                  flex: 5,
                  child: Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: AppTheme.bgSurface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppTheme.borderColor),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'GENERATE CUSTOM SOFTWARE',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 10),
                        TextField(
                          controller: _nameController,
                          style: const TextStyle(fontSize: 13, color: AppTheme.textMain),
                          decoration: InputDecoration(
                            labelText: 'App Name',
                            hintText: 'e.g. Dokonchi Inventory, Quick POS, Barcode Terminal',
                            filled: true,
                            fillColor: AppTheme.bgDark,
                            border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.borderColor)),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            DropdownButtonFormField<String>(
                              value: _category,
                              isExpanded: true,
                              dropdownColor: AppTheme.bgSurface,
                              style: const TextStyle(fontSize: 12, color: AppTheme.textMain),
                              decoration: InputDecoration(
                                labelText: 'Category',
                                contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                filled: true,
                                fillColor: AppTheme.bgDark,
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: AppTheme.borderColor)),
                              ),
                              items: _categories.map((c) => DropdownMenuItem(value: c, child: Text(c.toUpperCase()))).toList(),
                              onChanged: (val) => setState(() => _category = val ?? 'retail'),
                            ),
                            const SizedBox(height: 10),
                            ElevatedButton.icon(
                              onPressed: _isBuilding ? null : _handleBuildApp,
                              icon: const Icon(Icons.build_circle_outlined, size: 16),
                              label: const Text('Build App', style: TextStyle(fontWeight: FontWeight.bold)),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFFF59E0B),
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(vertical: 12),
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                              ),
                            ),
                          ],
                        ),
                        if (_statusMessage != null) ...[
                          const SizedBox(height: 10),
                          Text(_statusMessage!, style: const TextStyle(fontSize: 11, color: Color(0xFF10B981))),
                        ],
                        const SizedBox(height: 16),
                        const Divider(color: AppTheme.borderColor),
                        const Text(
                          'FORGE BUILT APPS',
                          style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 8),
                        Expanded(
                          child: _apps.isEmpty
                              ? const Center(child: Text('No custom apps generated yet. Build one above!', style: TextStyle(fontSize: 11, color: AppTheme.textMuted)))
                              : ListView.separated(
                                  itemCount: _apps.length,
                                  separatorBuilder: (_, __) => const Divider(color: AppTheme.borderColor, height: 1),
                                  itemBuilder: (context, idx) {
                                    final app = _apps[idx];
                                    final isSelected = _selectedApp?['id'] == app['id'];
                                    return ListTile(
                                      selected: isSelected,
                                      selectedTileColor: const Color(0xFFF59E0B).withValues(alpha: 0.1),
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                                      dense: true,
                                      leading: const Icon(Icons.dashboard_customize_outlined, size: 18, color: Color(0xFFF59E0B)),
                                      title: Text(app['name'] ?? '', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppTheme.textMain)),
                                      subtitle: Text('${app['category']} • ${app['data']?.length ?? 0} records • Zero-Vision', style: const TextStyle(fontSize: 10, color: AppTheme.textMuted)),
                                      onTap: () => setState(() => _selectedApp = app),
                                    );
                                  },
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 18),

                // Right: Zero-Vision Control Inspector & Live Data
                Expanded(
                  flex: 6,
                  child: Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: AppTheme.bgSurface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppTheme.borderColor),
                    ),
                    child: _selectedApp == null
                        ? const Center(child: Text('Select or generate an app to view its Zero-Vision schema', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)))
                        : Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        _selectedApp!['name'] ?? '',
                                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                                      ),
                                      Text(
                                        'Schema ID: ${_selectedApp!['id']} • Native Hook Enabled',
                                        style: const TextStyle(fontSize: 11, color: AppTheme.textMuted),
                                      ),
                                    ],
                                  ),
                                  const Spacer(),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF10B981).withValues(alpha: 0.15),
                                      borderRadius: BorderRadius.circular(6),
                                      border: Border.all(color: const Color(0xFF10B981).withValues(alpha: 0.3)),
                                    ),
                                    child: const Text('ZERO-VISION ACTIVE', style: TextStyle(fontSize: 10, color: Color(0xFF10B981), fontWeight: FontWeight.bold)),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              // Programmatic Actions Bar
                              Wrap(
                                spacing: 8,
                                children: [
                                  ActionChip(
                                    label: const Text('+ Insert Sample Record', style: TextStyle(fontSize: 11)),
                                    backgroundColor: AppTheme.bgDark,
                                    side: const BorderSide(color: AppTheme.borderColor),
                                    onPressed: () => _executeHook('add_record', {
                                      'sku': 'SKU-${DateTime.now().millisecondsSinceEpoch % 10000}',
                                      'title': 'Forge Live Item',
                                      'quantity': 10,
                                      'price': 24.99
                                    }),
                                  ),
                                  ActionChip(
                                    label: const Text('Update First Record', style: TextStyle(fontSize: 11)),
                                    backgroundColor: AppTheme.bgDark,
                                    side: const BorderSide(color: AppTheme.borderColor),
                                    onPressed: () => _executeHook('update_record', {
                                      'id_field': 'sku',
                                      'value': 'SKU-1001',
                                      'updates': {'quantity': 99}
                                    }),
                                  ),
                                  ActionChip(
                                    label: const Text('Clear All', style: TextStyle(fontSize: 11, color: AppTheme.danger)),
                                    backgroundColor: AppTheme.bgDark,
                                    side: const BorderSide(color: AppTheme.danger),
                                    onPressed: () => _executeHook('clear_all'),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 14),
                              const Text('Live Application Records', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.textMuted)),
                              const SizedBox(height: 6),
                              Expanded(
                                child: Container(
                                  decoration: BoxDecoration(
                                    color: AppTheme.bgDark,
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(color: AppTheme.borderColor),
                                  ),
                                  child: ListView(
                                    padding: const EdgeInsets.all(8),
                                    children: [
                                      for (final item in (_selectedApp!['data'] as List? ?? []))
                                        Container(
                                          margin: const EdgeInsets.only(bottom: 6),
                                          padding: const EdgeInsets.all(10),
                                          decoration: BoxDecoration(
                                            color: AppTheme.bgCard,
                                            borderRadius: BorderRadius.circular(6),
                                            border: Border.all(color: AppTheme.borderColor),
                                          ),
                                          child: Text(
                                            item.toString(),
                                            style: const TextStyle(fontSize: 11, fontFamily: 'monospace', color: AppTheme.textMain),
                                          ),
                                        ),
                                    ],
                                  ),
                                ),
                              ),
                            ],
                          ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
