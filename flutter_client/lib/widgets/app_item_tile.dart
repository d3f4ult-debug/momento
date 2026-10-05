import 'package:flutter/material.dart';
import '../models/app_info.dart';
import '../theme/app_theme.dart';

class AppItemTile extends StatelessWidget {
  final AppInfo app;
  final VoidCallback onLaunch;

  const AppItemTile({
    super.key,
    required this.app,
    required this.onLaunch,
  });

  IconData _getCategoryIcon(String cat) {
    switch (cat.toLowerCase()) {
      case 'internet':
      case 'browser':
        return Icons.language;
      case 'development':
      case 'code':
        return Icons.code;
      case 'system':
        return Icons.terminal;
      case 'graphics':
        return Icons.brush;
      default:
        return Icons.apps;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.bgSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.borderColor.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: AppTheme.bgCard,
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(
              _getCategoryIcon(app.category),
              size: 16,
              color: AppTheme.accentLight,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  app.name,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: AppTheme.textMain,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  '${app.category} • ${app.id}',
                  style: const TextStyle(
                    fontSize: 11,
                    color: AppTheme.textMuted,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          ElevatedButton(
            onPressed: onLaunch,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.accent.withValues(alpha: 0.2),
              foregroundColor: AppTheme.accentLight,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              elevation: 0,
              side: BorderSide(color: AppTheme.accent.withValues(alpha: 0.4)),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
            ),
            child: const Text('Launch', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}
