# Infinity Algorithm Canonical

Support system (inputs, observation, feedback): `docs/roadmap/INFINITY_ALGORITHM_SUPPORT_SYSTEM.md`.

## 1. Symbol Definitions

Let \(t \in \mathbb{T}\) denote discrete decision times with increment \(\Delta t > 0\).

- \(S_t\): system state at time \(t\).
- \(I_t\): input set at time \(t\).
- \(M_t\): memory state at time \(t\).
- \(T\): transformation operator.
- \(C\): constraint operator.
- \(R\): recurrence operator.
- \(O_t\): output set at time \(t\).
- \(P\): projection function (optional).
- \(f_{score}\): scoring function family.
- \(\Delta t\): time delta between two consecutive evaluations.

Auxiliary notation:

- \(\mathcal{S}\): state space, \(S_t \in \mathcal{S}\).
- \(\mathcal{I}\): input space, \(I_t \in \mathcal{I}\).
- \(\mathcal{O}\): output space, \(O_t \in \mathcal{O}\).
- \(U_t\): deterministic update sub-operator.
- \(Q_t\): probabilistic inference sub-operator.
- \(E_t\): metric evaluation sub-operator.

## 2. State Space Definition

\[
S_t = (\mathrm{Tasks}_t,\ \mathrm{Memory}_t,\ \mathrm{MasterplanState}_t,\ \mathrm{Metrics}_t,\ \mathrm{ExternalSignals}_t)
\]

with:

- \(\mathrm{Tasks}_t\): task entities and statuses.
- \(\mathrm{Memory}_t = M_t\): stored nodes, links, and historical context.
- \(\mathrm{MasterplanState}_t\): plan lifecycle and active-plan status.
- \(\mathrm{Metrics}_t\): scalar/vector evaluations computed from signals and state.
- \(\mathrm{ExternalSignals}_t\): exogenous observations available at time \(t\).

Persistence classes:

- Persistent components: \(\mathrm{Tasks}_t, \mathrm{Memory}_t, \mathrm{MasterplanState}_t\).
- Derived components: \(\mathrm{Metrics}_t\).
- Transient components: \(\mathrm{ExternalSignals}_t\) and intermediate computations not stored as state invariants.

Input space:

\[
I_t = I_t^{ext} \cup I_t^{int}
\]

where \(I_t^{ext}\) are external signals/events and \(I_t^{int}\) are internally generated triggers/summaries.

## 3. Transformation Layer

\[
S_t' = T(S_t, I_t)
\]

Decomposition:

\[
T = E_t \circ Q_t \circ U_t
\]

Deterministic transforms:

\[
U_t: \mathcal{S} \times \mathcal{I} \rightarrow \mathcal{S}
\]

Probabilistic transforms (model-based inference):

\[
Q_t: \mathcal{S} \times \mathcal{I} \rightarrow \mathcal{Z},\quad
z_t \sim p_{\theta}(z \mid S_t, I_t)
\]

Metric evaluation:

\[
E_t: (\mathcal{S}, \mathcal{Z}) \rightarrow \mathcal{S},\quad
\mathrm{Metrics}_t = f_{score}(S_t, I_t, z_t)
\]

Optional projection:

\[
P: \mathcal{S} \rightarrow \mathcal{Y},\quad
y_t = P(S_t)
\]

## 4. Constraint Layer

\[
S_t'' = C(S_t')
\]

Let \(C = C_{lock} \circ C_{uniq} \circ C_{perm} \circ C_{active}\), where:

- Lock constraints:
  \[
  C_{lock}(S)=S \text{ with forbidden mutations nullified on locked entities}
  \]
- Uniqueness constraints:
  \[
  C_{uniq}(S)\ \text{enforces uniqueness predicates on relation/entity keys}
  \]
- Permission validation constraints:
  \[
  C_{perm}(S)\ \text{accepts updates only if authorization predicates are true}
  \]
- Active-state enforcement:
  \[
  C_{active}(S)\ \text{enforces singleton active status where required}
  \]

## 5. Recurrence / Feedback Loop

\[
S_{t+1} = R(S_t'')
\]

with:

\[
R = R_{time} \circ R_{trigger} \circ R_{sched}
\]

- Time-based evaluation:
  \[
  R_{time}(S,\Delta t)\ \text{applies elapsed-time-dependent state updates}
  \]
- Triggered updates:
  \[
  R_{trigger}(S)\ \text{applies event-conditional transitions}
  \]
- Scheduled evaluation cycles:
  \[
  R_{sched}(S)\ \text{applies periodic transition checks at fixed cadence}
  \]

## 6. Objective Structure (If Derivable)

No global optimization objective explicitly implemented.

## 7. Deterministic vs Probabilistic Separation

Deterministic (pure or rule-constrained mappings):

- \(U_t\), \(C\), \(R_{time}\), \(R_{trigger}\), \(R_{sched}\), and deterministic components of \(f_{score}\).

Probabilistic (external model inference):

- \(Q_t\), producing \(z_t \sim p_{\theta}(z \mid S_t, I_t)\).

Potentially non-deterministic outputs:

\[
O_t = \mathrm{Output}(S_{t+1}, z_t)
\]

where non-determinism enters only through stochastic inference variables (or external stochastic inputs).

## 8. Canonical Loop Representation

```text
Initialize S_0
For each time step t:
    I_t <- external + internal signals
    S_t' <- T(S_t, I_t)
    S_t'' <- C(S_t')
    S_{t+1} <- R(S_t'')
    O_t <- Output(S_{t+1})
End loop
```
