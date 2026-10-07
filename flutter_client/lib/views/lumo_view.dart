import 'package:flutter/material.dart';
import '../services/bridge_service.dart';
import '../theme/app_theme.dart';

class LumoView extends StatefulWidget {
  final BridgeService bridgeService;

  const LumoView({super.key, required this.bridgeService});

  @override
  State<LumoView> createState() => _LumoViewState();
}

class _LumoViewState extends State<LumoView> {
  final _promptController = TextEditingController();
  String _selectedStyle = 'modern';
  String _selectedResolution = '512x512';
  bool _isGenerating = false;
  List<Map<String, dynamic>> _gallery = [];
  Map<String, dynamic>? _latestAsset;
  String? _statusMessage;

  final List<String> _styles = ['modern', 'photorealistic', 'cyberpunk', 'vector', 'minimalist', 'watercolor'];
  final List<String> _resolutions = ['512x512', '768x512', '512x768', '1024x1024'];

  @override
  void initState() {
    super.initState();
    _loadGallery();
  }

  @override
  void dispose() {
    _promptController.dispose();
    super.dispose();
  }

  Future<void> _loadGallery() async {
    final items = await widget.bridgeService.getLumoGallery();
    if (mounted) {
      setState(() {
        _gallery = items;
        if (_latestAsset == null && items.isNotEmpty) {
          _latestAsset = items.first;
        }
      });
    }
  }

  Future<void> _handleGenerate() async {
    final prompt = _promptController.text.trim();
    if (prompt.isEmpty || _isGenerating) return;

    setState(() {
      _isGenerating = true;
      _statusMessage = null;
    });

    try {
      final res = await widget.bridgeService.generateImage(
        prompt,
        style: _selectedStyle,
        resolution: _selectedResolution,
      );
      if (mounted) {
        if (res['success'] == true) {
          final asset = res['asset'] as Map<String, dynamic>?;
          setState(() {
            _latestAsset = asset;
            _statusMessage = res['message']?.toString() ?? 'Visual asset synthesized successfully.';
          });
          _loadGallery();
        } else {
          setState(() {
            _statusMessage = res['error']?.toString() ?? 'Generation failed.';
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _statusMessage = 'Generation error: $e');
      }
    } finally {
      if (mounted) {
        setState(() => _isGenerating = false);
      }
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
                  gradient: const LinearGradient(colors: [Color(0xFFEC4899), Color(0xFF8B5CF6)]),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.palette_outlined, color: Colors.white, size: 22),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Lumo — All-in-One Image Generation & Vision Suite',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      'Synthesize graphics, creative assets, and inspect visual UI components natively.',
                      style: TextStyle(fontSize: 12, color: AppTheme.textMuted),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.refresh, size: 18, color: AppTheme.textMuted),
                tooltip: 'Refresh Gallery',
                onPressed: _loadGallery,
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Main Workspace
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Left: Controls & Prompts
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
                          'VISUAL PROMPT',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _promptController,
                          maxLines: 4,
                          style: const TextStyle(fontSize: 13, color: AppTheme.textMain),
                          decoration: InputDecoration(
                            hintText: 'Describe visual asset or concept (e.g. Modern glassmorphism dashboard icon, cybernetic inventory tag)...',
                            hintStyle: const TextStyle(fontSize: 12, color: AppTheme.textMuted),
                            filled: true,
                            fillColor: AppTheme.bgDark,
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                              borderSide: const BorderSide(color: AppTheme.borderColor),
                            ),
                          ),
                        ),
                        const SizedBox(height: 14),

                        // Options
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const Text('Style Preset', style: TextStyle(fontSize: 11, color: AppTheme.textMuted)),
                            const SizedBox(height: 6),
                            DropdownButtonFormField<String>(
                              value: _selectedStyle,
                              isExpanded: true,
                              dropdownColor: AppTheme.bgSurface,
                              style: const TextStyle(fontSize: 12, color: AppTheme.textMain),
                              decoration: InputDecoration(
                                contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                filled: true,
                                fillColor: AppTheme.bgDark,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(6),
                                  borderSide: const BorderSide(color: AppTheme.borderColor),
                                ),
                              ),
                              items: _styles.map((s) => DropdownMenuItem(value: s, child: Text(s.toUpperCase()))).toList(),
                              onChanged: (val) => setState(() => _selectedStyle = val ?? 'modern'),
                            ),
                            const SizedBox(height: 10),
                            const Text('Resolution', style: TextStyle(fontSize: 11, color: AppTheme.textMuted)),
                            const SizedBox(height: 6),
                            DropdownButtonFormField<String>(
                              value: _selectedResolution,
                              isExpanded: true,
                              dropdownColor: AppTheme.bgSurface,
                              style: const TextStyle(fontSize: 12, color: AppTheme.textMain),
                              decoration: InputDecoration(
                                contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                filled: true,
                                fillColor: AppTheme.bgDark,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(6),
                                  borderSide: const BorderSide(color: AppTheme.borderColor),
                                ),
                              ),
                              items: _resolutions.map((r) => DropdownMenuItem(value: r, child: Text(r))).toList(),
                              onChanged: (val) => setState(() => _selectedResolution = val ?? '512x512'),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),

                        ElevatedButton.icon(
                          onPressed: _isGenerating ? null : _handleGenerate,
                          icon: _isGenerating
                              ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                              : const Icon(Icons.auto_fix_high, size: 16),
                          label: Text(_isGenerating ? 'Synthesizing...' : 'Generate with Lumo', style: const TextStyle(fontWeight: FontWeight.bold)),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFFEC4899),
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 14),
                            minimumSize: const Size(double.infinity, 44),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                          ),
                        ),

                        if (_statusMessage != null) ...[
                          const SizedBox(height: 12),
                          Text(_statusMessage!, style: const TextStyle(fontSize: 11, color: Color(0xFF10B981))),
                        ],

                        const Spacer(),
                        const Divider(color: AppTheme.borderColor),
                        const Text(
                          'RECENT GALLERY ARTIFACTS',
                          style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 8),
                        SizedBox(
                          height: 70,
                          child: _gallery.isEmpty
                              ? const Center(child: Text('No assets in gallery yet', style: TextStyle(fontSize: 11, color: AppTheme.textMuted)))
                              : ListView.builder(
                                  scrollDirection: Axis.horizontal,
                                  itemCount: _gallery.length,
                                  itemBuilder: (context, idx) {
                                    final item = _gallery[idx];
                                    final isSelected = _latestAsset?['id'] == item['id'];
                                    return GestureDetector(
                                      onTap: () => setState(() => _latestAsset = item),
                                      child: Container(
                                        width: 70,
                                        margin: const EdgeInsets.only(right: 8),
                                        decoration: BoxDecoration(
                                          color: AppTheme.bgDark,
                                          borderRadius: BorderRadius.circular(6),
                                          border: Border.all(color: isSelected ? const Color(0xFFEC4899) : AppTheme.borderColor, width: isSelected ? 2 : 1),
                                        ),
                                        child: Center(
                                          child: Icon(Icons.image, size: 24, color: isSelected ? const Color(0xFFEC4899) : AppTheme.textMuted),
                                        ),
                                      ),
                                    );
                                  },
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 18),

                // Right: Canvas Preview / Inspector
                Expanded(
                  flex: 6,
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
                        Row(
                          children: [
                            const Text(
                              'ASSET CANVAS & METADATA',
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                            ),
                            const Spacer(),
                            if (_latestAsset != null)
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                decoration: BoxDecoration(
                                  color: const Color(0xFFEC4899).withValues(alpha: 0.15),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Text(
                                  _latestAsset!['style']?.toString().toUpperCase() ?? 'VECTOR',
                                  style: const TextStyle(fontSize: 10, color: Color(0xFFEC4899), fontWeight: FontWeight.bold),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Expanded(
                          child: Center(
                            child: _latestAsset == null
                                ? const Column(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(Icons.image_outlined, size: 48, color: AppTheme.textMuted),
                                      SizedBox(height: 8),
                                      Text('Enter prompt on left to synthesize visual asset', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                                    ],
                                  )
                                : Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(16),
                                    decoration: BoxDecoration(
                                      color: AppTheme.bgDark,
                                      borderRadius: BorderRadius.circular(8),
                                      border: Border.all(color: AppTheme.borderColor),
                                    ),
                                    child: Column(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        const Icon(Icons.auto_awesome, size: 64, color: Color(0xFFEC4899)),
                                        const SizedBox(height: 14),
                                        Text(
                                          '"${_latestAsset!['prompt']}"',
                                          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                                          textAlign: TextAlign.center,
                                        ),
                                        const SizedBox(height: 8),
                                        Text(
                                          'Resolution: ${_latestAsset!['resolution']} • Format: SVG Vector • ID: ${_latestAsset!['id']}',
                                          style: const TextStyle(fontSize: 11, color: AppTheme.textMuted),
                                        ),
                                        const SizedBox(height: 16),
                                        Text(
                                          'Path: ${_latestAsset!['file_path']}',
                                          style: const TextStyle(fontSize: 10, color: AppTheme.textMuted, fontFamily: 'monospace'),
                                        ),
                                      ],
                                    ),
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
