import 'package:flutter/material.dart';
import '../models/chat_message.dart';
import '../theme/app_theme.dart';

class ExecutionCard extends StatefulWidget {
  final ExecutionResult result;
  final VoidCallback onStop;

  const ExecutionCard({
    super.key,
    required this.result,
    required this.onStop,
  });

  @override
  State<ExecutionCard> createState() => _ExecutionCardState();
}

class _ExecutionCardState extends State<ExecutionCard> {
  bool _isTerminalExpanded = true;
  final ScrollController _scrollController = ScrollController();

  @override
  void didUpdateWidget(covariant ExecutionCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.result.logs.length != oldWidget.result.logs.length) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scrollController.hasClients) {
          _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
        }
      });
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final res = widget.result;
    final isRunning = res.status.toLowerCase() == 'running';
    final runtimeLabel = res.runtime == 'local_native' ? 'Local Host' : 'Contabo VPS (Wine64)';

    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  res.binaryPath.isNotEmpty ? res.binaryPath : res.appName,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppTheme.textMain,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Wrap(
                spacing: 6,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: isRunning
                          ? AppTheme.success.withValues(alpha: 0.15)
                          : AppTheme.danger.withValues(alpha: 0.15),
                      border: Border.all(
                        color: isRunning
                            ? AppTheme.success.withValues(alpha: 0.4)
                            : AppTheme.danger.withValues(alpha: 0.4),
                      ),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      res.status.toUpperCase(),
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                        color: isRunning ? AppTheme.success : AppTheme.danger,
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppTheme.bgCard,
                      border: Border.all(color: AppTheme.borderColor),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      'PID: ${res.pid}',
                      style: const TextStyle(fontSize: 10, color: AppTheme.textMuted),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppTheme.bgCard,
                      border: Border.all(color: AppTheme.borderColor),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      runtimeLabel,
                      style: const TextStyle(fontSize: 10, color: AppTheme.accentLight),
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Session: ${res.sessionId}',
            style: const TextStyle(
              fontSize: 10,
              fontFamily: 'monospace',
              color: AppTheme.textMuted,
            ),
          ),
          const SizedBox(height: 8),
          // Terminal Output Stream
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Live Terminal Stream',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppTheme.textMuted),
              ),
              InkWell(
                onTap: () => setState(() => _isTerminalExpanded = !_isTerminalExpanded),
                child: Text(
                  _isTerminalExpanded ? 'Collapse' : 'Expand',
                  style: const TextStyle(fontSize: 10, color: AppTheme.accentLight),
                ),
              ),
            ],
          ),
          if (_isTerminalExpanded) ...[
            const SizedBox(height: 4),
            Container(
              height: 120,
              width: double.infinity,
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFF020617),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: const Color(0xFF1E293B)),
              ),
              child: res.logs.isEmpty
                  ? Text(
                      isRunning ? '[Process started • Listening for output...]' : '[No output logged]',
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 11,
                        color: Color(0xFF38BDF8),
                      ),
                    )
                  : ListView.builder(
                      controller: _scrollController,
                      itemCount: res.logs.length,
                      itemBuilder: (context, index) {
                        return Text(
                          res.logs[index],
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 11,
                            color: Color(0xFF38BDF8),
                          ),
                        );
                      },
                    ),
            ),
          ],
          if (isRunning) ...[
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerRight,
              child: ElevatedButton.icon(
                onPressed: widget.onStop,
                icon: const Icon(Icons.stop, size: 14),
                label: const Text('Stop Process', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.danger.withValues(alpha: 0.15),
                  foregroundColor: AppTheme.danger,
                  side: const BorderSide(color: AppTheme.danger, width: 0.8),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  elevation: 0,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
