import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../models/app_info.dart';
import '../models/session_info.dart';
import '../theme/app_theme.dart';
import 'app_item_tile.dart';
import 'session_item_card.dart';

class Sidebar extends StatefulWidget {
  final List<AppInfo> apps;
  final List<SessionInfo> sessions;
  final String executionMode;
  final String backendUrl;
  final Function(String mode) onModeChanged;
  final Function(AppInfo app) onLaunchApp;
  final Function(String sessionId) onStopSession;
  final VoidCallback onRescan;
  final VoidCallback onOpenSettings;
  final VoidCallback? onRegisterApp;
  final VoidCallback? onProfileApp;

  const Sidebar({
    super.key,
    required this.apps,
    required this.sessions,
    required this.executionMode,
    required this.backendUrl,
    required this.onModeChanged,
    required this.onLaunchApp,
    required this.onStopSession,
    required this.onRescan,
    required this.onOpenSettings,
    this.onRegisterApp,
    this.onProfileApp,
  });

  @override
  State<Sidebar> createState() => _SidebarState();
}

class _SidebarState extends State<Sidebar> {
  int _activeTabIndex = 0; // 0 = Apps, 1 = Sessions
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<AppInfo> get _filteredApps {
    if (_searchQuery.trim().isEmpty) return widget.apps;
    final q = _searchQuery.toLowerCase();
    return widget.apps.where((app) {
      return app.name.toLowerCase().contains(q) ||
          app.id.toLowerCase().contains(q) ||
          app.aliases.any((a) => a.toLowerCase().contains(q));
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 320,
      decoration: const BoxDecoration(
        color: AppTheme.bgSurface,
        border: Border(right: BorderSide(color: AppTheme.borderColor)),
      ),
      child: Column(
        children: [
          // Brand Header
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(colors: [AppTheme.accent, Color(0xFF8B5CF6)]),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: const Icon(Icons.layers, size: 16, color: Colors.white),
                    ),
                    const SizedBox(width: 8),
                    const Text(
                      'Momento',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textMain,
                        letterSpacing: -0.3,
                      ),
                    ),
                  ],
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: AppTheme.success.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(color: AppTheme.success.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(
                          color: AppTheme.success,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 5),
                      Text(
                        widget.executionMode == AppConfig.modeLocal ? 'Local Host' : 'VPS Core',
                        style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTheme.success),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),

          // Execution Mode Pills Bar
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'EXECUTION TARGET',
                  style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                ),
                const SizedBox(height: 6),
                Container(
                  padding: const EdgeInsets.all(3),
                  decoration: BoxDecoration(
                    color: AppTheme.bgDark,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppTheme.borderColor),
                  ),
                  child: Row(
                    children: [
                      _buildModeButton('Hybrid Auto', AppConfig.modeHybrid),
                      _buildModeButton('Local Host', AppConfig.modeLocal),
                      _buildModeButton('VPS Sandbox', AppConfig.modeVps),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),

          // Tabs
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: AppTheme.borderColor)),
            ),
            child: Row(
              children: [
                _buildTabButton(0, 'Indexed Apps', widget.apps.length),
                _buildTabButton(1, 'Sessions', widget.sessions.length),
              ],
            ),
          ),

          // Tab Content
          Expanded(
            child: _activeTabIndex == 0 ? _buildAppsTab() : _buildSessionsTab(),
          ),

          // Footer
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                if (widget.onRegisterApp != null) ...[
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: widget.onRegisterApp,
                      icon: const Icon(Icons.add_circle_outline, size: 14, color: AppTheme.accent),
                      label: const Text('+ Teach Custom App', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.accent)),
                      style: OutlinedButton.styleFrom(
                        backgroundColor: AppTheme.accent.withValues(alpha: 0.08),
                        side: BorderSide(color: AppTheme.accent.withValues(alpha: 0.4)),
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                if (widget.onProfileApp != null) ...[
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: widget.onProfileApp,
                      icon: const Icon(Icons.psychology_outlined, size: 14, color: Color(0xFF10B981)),
                      label: const Text('⚡ Profile & Learn App', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFF10B981))),
                      style: OutlinedButton.styleFrom(
                        backgroundColor: const Color(0xFF10B981).withValues(alpha: 0.08),
                        side: BorderSide(color: const Color(0xFF10B981).withValues(alpha: 0.4)),
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: widget.onRescan,
                        icon: const Icon(Icons.refresh, size: 14),
                        label: const Text('Rescan Apps', style: TextStyle(fontSize: 11)),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppTheme.textMain,
                          side: const BorderSide(color: AppTheme.borderColor),
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: widget.onOpenSettings,
                        icon: const Icon(Icons.settings, size: 14),
                        label: const Text('Settings', style: TextStyle(fontSize: 11)),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppTheme.textMain,
                          side: const BorderSide(color: AppTheme.borderColor),
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildModeButton(String title, String modeKey) {
    final isSelected = widget.executionMode == modeKey;
    return Expanded(
      child: InkWell(
        onTap: () => widget.onModeChanged(modeKey),
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 6),
          decoration: BoxDecoration(
            color: isSelected ? AppTheme.accent : Colors.transparent,
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            title,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 10,
              fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
              color: isSelected ? Colors.white : AppTheme.textMuted,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTabButton(int index, String title, int count) {
    final isActive = _activeTabIndex == index;
    return Expanded(
      child: InkWell(
        onTap: () => setState(() => _activeTabIndex = index),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: isActive ? AppTheme.accent : Colors.transparent,
                width: 2,
              ),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Flexible(
                child: Text(
                  title,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
                    color: isActive ? AppTheme.textMain : AppTheme.textMuted,
                  ),
                ),
              ),
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(
                  color: AppTheme.bgCard,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  '$count',
                  style: const TextStyle(fontSize: 10, color: AppTheme.textMuted),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAppsTab() {
    final apps = _filteredApps;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _searchController,
                  onChanged: (val) => setState(() => _searchQuery = val),
                  style: const TextStyle(fontSize: 12),
                  decoration: InputDecoration(
                    isDense: true,
                    hintText: 'Search applications...',
                    prefixIcon: const Icon(Icons.search, size: 16, color: AppTheme.textMuted),
                    suffixIcon: _searchQuery.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, size: 14),
                            onPressed: () {
                              _searchController.clear();
                              setState(() => _searchQuery = '');
                            },
                          )
                        : null,
                  ),
                ),
              ),
              if (widget.onRegisterApp != null) ...[
                const SizedBox(width: 6),
                IconButton(
                  tooltip: 'Teach / Register Custom App',
                  style: IconButton.styleFrom(
                    backgroundColor: AppTheme.bgCard,
                    padding: const EdgeInsets.all(8),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(6),
                      side: const BorderSide(color: AppTheme.borderColor),
                    ),
                  ),
                  icon: const Icon(Icons.add, size: 16, color: AppTheme.accent),
                  onPressed: widget.onRegisterApp,
                ),
              ],
            ],
          ),
        ),
        Expanded(
          child: apps.isEmpty
              ? const Center(
                  child: Text(
                    'No applications found.\nClick "Rescan Apps" below.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: AppTheme.textMuted),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  itemCount: apps.length,
                  itemBuilder: (context, index) {
                    final app = apps[index];
                    return AppItemTile(
                      app: app,
                      onLaunch: () => widget.onLaunchApp(app),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildSessionsTab() {
    if (widget.sessions.isEmpty) {
      return const Center(
        child: Text(
          'No active execution sessions.',
          style: TextStyle(fontSize: 12, color: AppTheme.textMuted),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: widget.sessions.length,
      itemBuilder: (context, index) {
        final session = widget.sessions[index];
        return SessionItemCard(
          session: session,
          onStop: () => widget.onStopSession(session.sessionId),
        );
      },
    );
  }
}
