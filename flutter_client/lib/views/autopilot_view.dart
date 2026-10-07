import 'package:flutter/material.dart';
import '../services/bridge_service.dart';
import '../theme/app_theme.dart';

class AutopilotView extends StatefulWidget {
  final BridgeService bridgeService;

  const AutopilotView({super.key, required this.bridgeService});

  @override
  State<AutopilotView> createState() => _AutopilotViewState();
}

class _AutopilotViewState extends State<AutopilotView> {
  final _taskNameController = TextEditingController();
  final _targetAppController = TextEditingController();
  bool _isEnqueuing = false;
  List<Map<String, dynamic>> _tasks = [];
  Map<String, dynamic>? _selectedTask;
  String? _statusMessage;

  @override
  void initState() {
    super.initState();
    _loadTasks();
  }

  @override
  void dispose() {
    _taskNameController.dispose();
    _targetAppController.dispose();
    super.dispose();
  }

  Future<void> _loadTasks() async {
    final list = await widget.bridgeService.listAutopilotTasks();
    if (mounted) {
      setState(() {
        _tasks = list;
        if (_selectedTask == null && list.isNotEmpty) {
          _selectedTask = list.first;
        }
      });
    }
  }

  Future<void> _handleEnqueue() async {
    final name = _taskNameController.text.trim();
    if (name.isEmpty || _isEnqueuing) return;

    setState(() {
      _isEnqueuing = true;
      _statusMessage = null;
    });

    try {
      final res = await widget.bridgeService.enqueueAutopilotWorkflow(
        name,
        targetApp: _targetAppController.text.trim().isEmpty ? null : _targetAppController.text.trim(),
      );
      if (mounted) {
        if (res['success'] == true) {
          final task = res['task'] as Map<String, dynamic>?;
          setState(() {
            _selectedTask = task;
            _statusMessage = res['message']?.toString() ?? 'Workflow enqueued in background.';
            _taskNameController.clear();
          });
          _loadTasks();
        } else {
          setState(() => _statusMessage = res['error']?.toString() ?? 'Failed to enqueue task.');
        }
      }
    } catch (e) {
      if (mounted) setState(() => _statusMessage = 'Enqueue error: $e');
    } finally {
      if (mounted) setState(() => _isEnqueuing = false);
    }
  }

  Future<void> _cancelTask(String taskId) async {
    final ok = await widget.bridgeService.cancelAutopilotTask(taskId);
    if (mounted && ok) {
      setState(() => _statusMessage = 'Task $taskId canceled.');
      _loadTasks();
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
                  gradient: const LinearGradient(colors: [Color(0xFF8B5CF6), Color(0xFF6366F1)]),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.rocket_launch, color: Colors.white, size: 22),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Autopilot — Autonomous Background Digital Worker',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      'Asynchronous task queue, scheduled routines, and background business automation.',
                      style: TextStyle(fontSize: 12, color: AppTheme.textMuted),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.refresh, size: 18, color: AppTheme.textMuted),
                tooltip: 'Refresh Task Queue',
                onPressed: _loadTasks,
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Main Workspace
          Expanded(
            child: Row(
              children: [
                // Left: Task Creator & Queue
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
                          'ENQUEUE WORKFLOW ROUTINE',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 10),
                        TextField(
                          controller: _taskNameController,
                          style: const TextStyle(fontSize: 13, color: AppTheme.textMain),
                          decoration: InputDecoration(
                            labelText: 'Workflow Task Name',
                            hintText: 'e.g. Daily Inventory Sync, Automated Backup, POS Reconciliation',
                            filled: true,
                            fillColor: AppTheme.bgDark,
                            border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.borderColor)),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            TextField(
                              controller: _targetAppController,
                              style: const TextStyle(fontSize: 12, color: AppTheme.textMain),
                              decoration: InputDecoration(
                                labelText: 'Target Application (Optional)',
                                hintText: 'e.g. Dokonchi or Forge App',
                                filled: true,
                                fillColor: AppTheme.bgDark,
                                contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: AppTheme.borderColor)),
                              ),
                            ),
                            const SizedBox(height: 10),
                            ElevatedButton.icon(
                              onPressed: _isEnqueuing ? null : _handleEnqueue,
                              icon: const Icon(Icons.play_arrow, size: 16),
                              label: const Text('Enqueue Task', style: TextStyle(fontWeight: FontWeight.bold)),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF8B5CF6),
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
                          'TASK QUEUE & EXECUTIONS',
                          style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 8),
                        Expanded(
                          child: _tasks.isEmpty
                              ? const Center(child: Text('Task queue empty. Enqueue a workflow above!', style: TextStyle(fontSize: 11, color: AppTheme.textMuted)))
                              : ListView.separated(
                                  itemCount: _tasks.length,
                                  separatorBuilder: (_, __) => const Divider(color: AppTheme.borderColor, height: 1),
                                  itemBuilder: (context, idx) {
                                    final task = _tasks[idx];
                                    final isSelected = _selectedTask?['id'] == task['id'];
                                    final status = task['status']?.toString() ?? 'completed';
                                    return ListTile(
                                      selected: isSelected,
                                      selectedTileColor: const Color(0xFF8B5CF6).withValues(alpha: 0.1),
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                                      dense: true,
                                      leading: Icon(
                                        status == 'running' ? Icons.sync : (status == 'completed' ? Icons.check_circle : Icons.schedule),
                                        size: 18,
                                        color: status == 'completed' ? const Color(0xFF10B981) : const Color(0xFF8B5CF6),
                                      ),
                                      title: Text(task['name'] ?? '', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppTheme.textMain)),
                                      subtitle: Text('${task['target_app']} • ${task['total_steps'] ?? 0} steps • Status: $status', style: const TextStyle(fontSize: 10, color: AppTheme.textMuted)),
                                      trailing: status == 'running'
                                          ? IconButton(
                                              icon: const Icon(Icons.cancel, size: 16, color: AppTheme.danger),
                                              onPressed: () => _cancelTask(task['id']),
                                            )
                                          : null,
                                      onTap: () => setState(() => _selectedTask = task),
                                    );
                                  },
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 18),

                // Right: Task Telemetry & Live Execution Logs
                Expanded(
                  flex: 6,
                  child: Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: AppTheme.bgSurface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppTheme.borderColor),
                    ),
                    child: _selectedTask == null
                        ? const Center(child: Text('Select a task to inspect execution progress and telemetry logs', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)))
                        : Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        _selectedTask!['name'] ?? '',
                                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                                      ),
                                      Text(
                                        'Task ID: ${_selectedTask!['id']} • Target: ${_selectedTask!['target_app']}',
                                        style: const TextStyle(fontSize: 11, color: AppTheme.textMuted),
                                      ),
                                    ],
                                  ),
                                  const Spacer(),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF8B5CF6).withValues(alpha: 0.15),
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      _selectedTask!['status']?.toString().toUpperCase() ?? 'COMPLETED',
                                      style: const TextStyle(fontSize: 10, color: Color(0xFF8B5CF6), fontWeight: FontWeight.bold),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 14),
                              ClipRRect(
                                borderRadius: BorderRadius.circular(4),
                                child: LinearProgressIndicator(
                                  value: (_selectedTask!['progress'] as num?)?.toDouble() ?? 1.0,
                                  backgroundColor: AppTheme.bgDark,
                                  valueColor: const AlwaysStoppedAnimation(Color(0xFF8B5CF6)),
                                  minHeight: 6,
                                ),
                              ),
                              const SizedBox(height: 14),
                              const Text('WORKFLOW TELEMETRY & EXECUTION LOGS', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.textMuted)),
                              const SizedBox(height: 8),
                              Expanded(
                                child: Container(
                                  width: double.infinity,
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: AppTheme.bgDark,
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(color: AppTheme.borderColor),
                                  ),
                                  child: ListView(
                                    children: [
                                      for (final line in (_selectedTask!['logs'] as List? ?? []))
                                        Padding(
                                          padding: const EdgeInsets.only(bottom: 4),
                                          child: Text(
                                            line.toString(),
                                            style: const TextStyle(fontSize: 11, fontFamily: 'monospace', color: Color(0xFF94A3B8)),
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
