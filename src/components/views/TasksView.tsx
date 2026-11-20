import { memo, useMemo, useState } from 'react';
import { ORCHESTRATION_PIPELINE } from '../../data/architectureSpec';
import { NexusStatus, RegisteredProject, TaskPriority, TaskRecord } from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface TasksViewProps {
  tasks: TaskRecord[];
  projects: RegisteredProject[];
  demoMode: boolean;
  daemonAuthenticated?: boolean;
  onCreateDraftTask: (
    title: string,
    projectId: string,
    priority?: TaskPriority,
    agentId?: string
  ) => void;
  onTaskControl: (
    taskId: string,
    action: 'execute' | 'approve' | 'reject' | 'pause' | 'resume' | 'cancel' | 'rollback'
  ) => void;
  onLoadDemoFixture: () => void;
}

const DEFAULT_VISIBLE_TASKS = 40;

export const TasksView = memo(function TasksView({
  tasks,
  projects,
  demoMode,
  daemonAuthenticated = false,
  onCreateDraftTask,
  onTaskControl,
  onLoadDemoFixture,
}: TasksViewProps) {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(tasks[0]?.id ?? null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskPriority, setTaskPriority] = useState<TaskPriority>('normal');
  const [agentId, setAgentId] = useState('operator');
  const [targetProjectId, setTargetProjectId] = useState(projects[0]?.id ?? '');

  const selectedTask = useMemo(
    () => tasks.find((t) => t.id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks]
  );

  const visibleTasks = useMemo(
    () => (showAllTasks ? tasks : tasks.slice(0, DEFAULT_VISIBLE_TASKS)),
    [showAllTasks, tasks]
  );

  const formattedReport = useMemo(
    () => (selectedTask?.report ? JSON.stringify(selectedTask.report, null, 2) : null),
    [selectedTask]
  );

  const joinedLogs = useMemo(
    () => (selectedTask ? selectedTask.logs.join('\n') : ''),
    [selectedTask]
  );

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const projectId = targetProjectId || projects[0]?.id;
    if (!taskTitle.trim() || !projectId) return;
    onCreateDraftTask(taskTitle.trim(), projectId, taskPriority, agentId.trim() || 'operator');
    setTaskTitle('');
    setShowCreateForm(false);
  };

  return (
    <div className="space-y-8">
      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1.5 max-w-3xl">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">
            Task Manager & Autonomous Orchestration
          </h2>
          <p className="text-sm text-[#94A3B8]">
            Inspect multi-phase execution plans, checkpoint status, permission approval gates,
            operation logs, and task controls. Live execution requires a connected Python
            orchestrator and active engine adapter.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 shrink-0">
          {!demoMode && tasks.length === 0 && (
            <button
              type="button"
              onClick={onLoadDemoFixture}
              className="px-3.5 py-2 text-xs font-medium rounded-md border border-[#1E293B] bg-[#121923] text-[#94A3B8] hover:text-[#F1F5F9] hover:border-[#3987F5] transition-colors whitespace-nowrap shrink-0"
            >
              Load Demo Task Plan
            </button>
          )}
          <button
            type="button"
            disabled={projects.length === 0}
            onClick={() => setShowCreateForm((v) => !v)}
            className="px-4 py-2 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] disabled:opacity-40 transition-colors whitespace-nowrap shrink-0"
          >
            {showCreateForm ? 'Cancel Draft' : 'Create Task Draft'}
          </button>
        </div>
      </section>

      {showCreateForm && projects.length > 0 && (
        <form
          onSubmit={handleCreate}
          className="p-5 rounded-lg bg-[#121923] border border-[#35D6C5]/40 space-y-4"
        >
          <div className="text-sm font-semibold text-[#F1F5F9]">New Autonomous Task Plan Draft</div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
            <label className="md:col-span-2 space-y-1">
              <span className="text-[#94A3B8]">Development Objective</span>
              <input
                type="text"
                required
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
                placeholder="e.g. Audit PlayerController physics layers and verify scene build"
                className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[#94A3B8]">Target Project</span>
              <select
                value={targetProjectId || projects[0]?.id}
                onChange={(e) => setTargetProjectId(e.target.value)}
                className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.engine})
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[#94A3B8]">Priority</span>
              <select
                value={taskPriority}
                onChange={(e) => setTaskPriority(e.target.value as TaskPriority)}
                className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </label>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs items-end">
            <label className="space-y-1">
              <span className="text-[#94A3B8]">Initiating Agent / Client ID</span>
              <input
                type="text"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                placeholder="operator"
                className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
              />
            </label>
            <div className="md:col-span-3 flex justify-end">
              <button
                type="submit"
                className="px-4 py-2 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] transition-colors whitespace-nowrap shrink-0"
              >
                Generate Execution Plan
              </button>
            </div>
          </div>
        </form>
      )}

      {selectedTask ? (
        <section className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
          <div className="xl:col-span-5 space-y-4">
            <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
              Task Queue ({tasks.length})
            </h3>
            <div className="space-y-3">
              {visibleTasks.map((task) => {
                const active = selectedTask.id === task.id;
                let readySteps = 0;
                for (let idx = 0; idx < task.steps.length; idx++) {
                  const st = task.steps[idx].status;
                  if (st === NexusStatus.Available || st === NexusStatus.Connected) {
                    readySteps++;
                  }
                }
                return (
                  <button
                    key={task.id}
                    type="button"
                    onClick={() => setSelectedTaskId(task.id)}
                    className={`w-full text-left p-4 rounded-lg border transition-colors space-y-2 ${
                      active
                        ? 'bg-[#182230] border-[#35D6C5]/50'
                        : 'bg-[#121923] border-[#1E293B] hover:border-[#3987F5]/40'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="font-medium text-sm text-[#F1F5F9]">{task.title}</div>
                      <StatusText status={task.status} />
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-[#94A3B8]">
                      <span>{task.projectName}</span>
                      <span aria-hidden="true">·</span>
                      <span>{task.engine}</span>
                      <span aria-hidden="true">·</span>
                      <span className="capitalize">{task.priority ?? 'normal'}</span>
                      <span aria-hidden="true">·</span>
                      <span className="font-mono tabular-nums">
                        {readySteps}/{task.steps.length} steps ({task.progress ?? 0}%)
                      </span>
                    </div>
                  </button>
                );
              })}
              {tasks.length > DEFAULT_VISIBLE_TASKS && (
                <button
                  type="button"
                  onClick={() => setShowAllTasks((prev) => !prev)}
                  className="w-full py-2 text-xs font-medium text-[#35D6C5] rounded-lg border border-[#1E293B] bg-[#121923] hover:border-[#35D6C5]/50 transition-colors"
                >
                  {showAllTasks
                    ? `Show first ${DEFAULT_VISIBLE_TASKS} tasks`
                    : `Show all ${tasks.length} tasks`}
                </button>
              )}
            </div>
          </div>

          <div className="xl:col-span-7 space-y-6">
            <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-[#94A3B8]">
                    {selectedTask.isDemoFixture
                      ? 'Demonstration Task Plan'
                      : 'Autonomous Task Plan'}{' '}
                    · <span className="font-mono">{selectedTask.id}</span> ·{' '}
                    <span className="capitalize">{selectedTask.priority ?? 'normal'} priority</span>{' '}
                    · <span>Agent: {selectedTask.agentId ?? 'operator'}</span>
                  </div>
                  <h3 className="font-display text-base font-semibold text-[#F1F5F9] mt-0.5">
                    {selectedTask.title}
                  </h3>
                </div>
                <StatusText status={selectedTask.status} />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-[#94A3B8] pt-1">
                <div>
                  Progress:{' '}
                  <span className="font-mono tabular-nums text-[#F1F5F9]">
                    {selectedTask.progress ?? 0}%
                  </span>
                </div>
                <div>
                  Checkpoint:{' '}
                  <span className="font-mono text-[#F1F5F9]">
                    {selectedTask.checkpointId ?? 'None created'}
                  </span>
                </div>
                <div>
                  Repairs:{' '}
                  <span className="font-mono tabular-nums text-[#F1F5F9]">
                    {selectedTask.retryAttempts ?? 0}/{selectedTask.maxRepairAttempts ?? 3}
                  </span>
                </div>
              </div>

              <div className="text-xs text-[#94A3B8]">
                <span className="text-[#F1F5F9] font-medium">Current Operation: </span>
                {selectedTask.currentOperation}
              </div>

              {selectedTask.approvalPending && (
                <div className="p-3.5 rounded bg-[#1F1A10] border border-[#D99B38]/50 space-y-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-[#F4BF64]">
                      Checkpoint Approval Gate Required
                    </span>
                    <span className="font-mono text-[#D99B38]">
                      {selectedTask.approvalPending.requiredScopes.join(', ')}
                    </span>
                  </div>
                  <p className="text-[#F1F5F9] leading-relaxed">
                    {selectedTask.approvalPending.reason}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <button
                      type="button"
                      disabled={!daemonAuthenticated || Boolean(selectedTask.isDemoFixture)}
                      onClick={() => onTaskControl(selectedTask.id, 'approve')}
                      className="px-3 py-1.5 font-semibold rounded bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] disabled:opacity-40 transition-colors whitespace-nowrap"
                    >
                      Approve &amp; Resume
                    </button>
                    <button
                      type="button"
                      disabled={!daemonAuthenticated || Boolean(selectedTask.isDemoFixture)}
                      onClick={() => onTaskControl(selectedTask.id, 'reject')}
                      className="px-3 py-1.5 font-medium rounded border border-[#E5534B]/40 text-[#E5534B] hover:bg-[#E5534B]/10 disabled:opacity-40 transition-colors whitespace-nowrap"
                    >
                      Reject Gate
                    </button>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[#1E293B]">
                <button
                  type="button"
                  disabled={
                    !daemonAuthenticated ||
                    Boolean(selectedTask.isDemoFixture) ||
                    selectedTask.status === NexusStatus.Running
                  }
                  onClick={() => onTaskControl(selectedTask.id, 'execute')}
                  className="px-3 py-1.5 text-xs font-semibold rounded bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] disabled:opacity-40 transition-colors whitespace-nowrap shrink-0"
                >
                  Execute Task
                </button>
                <button
                  type="button"
                  onClick={() => onTaskControl(selectedTask.id, 'pause')}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-[#1E293B] bg-[#0B0F14] text-[#F1F5F9] hover:border-[#3987F5] transition-colors whitespace-nowrap shrink-0"
                >
                  Pause
                </button>
                <button
                  type="button"
                  onClick={() => onTaskControl(selectedTask.id, 'resume')}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-[#1E293B] bg-[#0B0F14] text-[#F1F5F9] hover:border-[#35D6C5] transition-colors whitespace-nowrap shrink-0"
                >
                  Resume
                </button>
                <button
                  type="button"
                  onClick={() => onTaskControl(selectedTask.id, 'cancel')}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-[#E5534B]/40 text-[#E5534B] hover:bg-[#E5534B]/10 transition-colors whitespace-nowrap shrink-0"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => onTaskControl(selectedTask.id, 'rollback')}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-[#D99B38]/40 text-[#F4BF64] hover:bg-[#D99B38]/10 transition-colors whitespace-nowrap shrink-0"
                >
                  Rollback Checkpoint
                </button>
              </div>
            </div>

            {formattedReport && (
              <div className="p-4 rounded-lg bg-[#121923] border border-[#1E293B] space-y-2">
                <div className="text-xs font-semibold text-[#F1F5F9]">Completion Report</div>
                <pre className="p-3 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-xs text-[#94A3B8] overflow-x-auto leading-relaxed">
                  {formattedReport}
                </pre>
              </div>
            )}

            <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                    <th className="py-2.5 px-4 w-14">Step</th>
                    <th className="py-2.5 px-4">Phase</th>
                    <th className="py-2.5 px-4">Gate</th>
                    <th className="py-2.5 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1E293B] text-xs">
                  {selectedTask.steps.map((step) => (
                    <tr key={step.stepNumber} className="hover:bg-[#161F2C]">
                      <td className="py-2 px-4 font-mono tabular-nums text-[#35D6C5]">
                        {String(step.stepNumber).padStart(2, '0')}
                      </td>
                      <td className="py-2 px-4">
                        <div className="font-medium text-[#F1F5F9]">{step.name}</div>
                        <div className="text-[#94A3B8]">{step.subsystem}</div>
                      </td>
                      <td className="py-2 px-4 whitespace-nowrap">
                        {step.gateRequired ? (
                          <span className="text-[#D99B38]">Approval Gate</span>
                        ) : (
                          <span className="text-[#94A3B8]">Auto</span>
                        )}
                      </td>
                      <td className="py-2 px-4 whitespace-nowrap">
                        <StatusText status={step.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="p-4 rounded-lg bg-[#121923] border border-[#1E293B] space-y-2">
              <div className="text-xs font-semibold text-[#F1F5F9]">Task Execution Log</div>
              <pre className="p-3 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-xs text-[#94A3B8] overflow-x-auto leading-relaxed">
                {joinedLogs}
              </pre>
            </div>
          </div>
        </section>
      ) : (
        <section className="space-y-6">
          <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="text-sm font-medium text-[#F1F5F9]">Active Task Queue: 0 Tasks</div>
              <p className="text-xs text-[#94A3B8]">
                {projects.length === 0
                  ? 'Register a project or load the demonstration fixture to inspect a task plan.'
                  : 'Click Create Task Draft above to scaffold a 12-step execution plan for a registered project.'}
              </p>
            </div>
            <StatusText
              status={daemonAuthenticated ? NexusStatus.Available : NexusStatus.Disconnected}
            />
          </div>

          <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                  <th className="py-3 px-4 w-16">Step</th>
                  <th className="py-3 px-4">Phase</th>
                  <th className="py-3 px-4">Subsystem</th>
                  <th className="py-3 px-4">Responsibility</th>
                  <th className="py-3 px-4">Gate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E293B] text-sm">
                {ORCHESTRATION_PIPELINE.map((step) => (
                  <tr key={step.stepNumber} className="hover:bg-[#161F2C]">
                    <td className="py-2.5 px-4 font-mono text-xs tabular-nums text-[#35D6C5]">
                      {String(step.stepNumber).padStart(2, '0')}
                    </td>
                    <td className="py-2.5 px-4 font-medium text-[#F1F5F9] whitespace-nowrap">
                      {step.name}
                    </td>
                    <td className="py-2.5 px-4 text-xs text-[#94A3B8] whitespace-nowrap">
                      {step.subsystem}
                    </td>
                    <td className="py-2.5 px-4 text-xs text-[#94A3B8]">{step.description}</td>
                    <td className="py-2.5 px-4 text-xs whitespace-nowrap">
                      {step.gateRequired ? (
                        <span className="text-[#D99B38] font-medium">Policy Gate</span>
                      ) : (
                        <span className="text-[#94A3B8]">Automatic</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
});
