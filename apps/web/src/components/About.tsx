import { RouteGuide } from "./RunPanel";

/** "How it works": what the service does, why it is hard, and how anyone can check its work. Plain words for an
 * analyst first; the names an examiner looks for (agents, tools, verification, trace) are all here too. */
const STEPS: { name: string; what: string }[] = [
  { name: "Ingestion gate", what: "Checks the request against the published data contract: every field, type, range and "
      + "cross-field rule. A malformed request is refused with an error per field and kept in quarantine; no check starts "
      + "for it. The gate also applies the per-client rate limit." },
  { name: "Queue", what: "An accepted request gets a run id at once and waits in a queue for a worker, so a slow check "
      + "never holds up the page. Workers can be scaled out." },
  { name: "Guardrails", what: "Every free-text field on the label is treated as untrusted. Text that tries to give the "
      + "system instructions (prompt injection) is flagged, and the check escalates instead of acting on it." },
  { name: "Classifier", what: "Decides the product category and lists every claim printed on the pack. A category outside "
      + "the two regulations' scope is escalated, not guessed." },
  { name: "Researcher", what: "Searches the regulation text as a tool, once per requirement. It follows each claim into "
      + "the regulation that sets its condition, checks whether another provision modifies what it found, and searches "
      + "again with what it has just read." },
  { name: "Verifier", what: "Checks that every quote is word for word in a passage retrieved in this run, under the "
      + "clause it names, and re-derives numeric conditions from the declared values. If anything is unsupported, the "
      + "researcher tries again with a hint, up to three attempts in all, and then the check escalates." },
  { name: "Router", what: "Turns the verified findings into one of three recommendations, with the reason." },
  { name: "Output filter", what: "Makes sure nothing in the result reads as an approval for print." },
];

export function About() {
  return (
    <article className="panel about" aria-labelledby="about-title">
      <h2 id="about-title">How FSSAI Label Check works</h2>
      <p className="about__lede">
        You describe a proposed packaged-food label as text: what is printed on the pack, its claims, the nutrition
        panel and the pack size. The service checks it against two FSSAI regulations and returns a finding for every
        requirement it checked, each with the exact regulation text it rests on, and one recommendation for what to do
        next. It never approves a label. A regulatory affairs professional decides.
      </p>

      <section aria-labelledby="about-sources">
        <h3 id="about-sources">What it checks against</h3>
        <ul className="about__list">
          <li><span className="mono">FSS-LD-2020</span>: the Food Safety and Standards (Labelling and Display)
            Regulations, 2020. What must appear on a label.</li>
          <li><span className="mono">FSS-AC-2018</span>: the Food Safety and Standards (Advertising and Claims)
            Regulations, 2018. The conditions a claim must meet.</li>
        </ul>
        <p>Both are the official consolidated versions, with every amendment printed next to the text it replaces. The
          product category in scope is breakfast cereals; anything else is escalated.</p>
      </section>

      <section aria-labelledby="about-hard">
        <h3 id="about-hard">Why this is hard</h3>
        <p>
          The two regulations do not refer to each other. A pack that says &ldquo;Source of protein&rdquo; is governed by
          a condition in the Claims regulation, but the Labelling regulation, which a label question naturally leads to,
          never points there. A single search for the label&rsquo;s wording does not find the provision that decides
          the answer. The researcher is built to follow the claim across, and the verifier to refuse any answer the
          retrieved text does not support. Try the built-in example on the New check page to see it.
        </p>
      </section>

      <section aria-labelledby="about-steps">
        <h3 id="about-steps">What happens when you press Check label</h3>
        <dl className="about__steps">
          {STEPS.map((step) => (
            <div key={step.name}>
              <dt>{step.name}</dt>
              <dd>{step.what}</dd>
            </div>
          ))}
        </dl>
        <p>Every step is bounded: a run has a limit on steps, tool calls and time, and a run that reaches one ends
          as incomplete with its reason, routed to <span className="mono">regulatory-review</span>.</p>
      </section>

      <section aria-labelledby="about-result">
        <h3 id="about-result">What you get back</h3>
        <p>Each requirement is marked <strong>met</strong>, <strong>unmet</strong>, <strong>cannot determine</strong> or
          <strong> not applicable</strong>, with its citations: the regulation, the clause and the quoted words. The
          label as a whole gets one recommendation:</p>
        <RouteGuide />
      </section>

      <section aria-labelledby="about-check">
        <h3 id="about-check">How you can check its work</h3>
        <ul className="about__list">
          <li>Every quote in a finding was found word for word in a passage retrieved during that run. Open the
            <strong> Trace</strong> tab of any check to see each search, the passages it returned and which ones the
            findings quote.</li>
          <li>The trace also shows every agent step in order, with the prompt version, latency, tokens and cost.</li>
          <li>Any check can be shared by its address and opened again later, and given feedback that feeds the
            quality dashboard.</li>
        </ul>
      </section>

      <section aria-labelledby="about-never">
        <h3 id="about-never">What it will never do</h3>
        <ul className="about__list">
          <li>Approve a label for print, or word a result as if it had.</li>
          <li>State a regulation, clause or threshold it did not retrieve. When unsure it escalates: declining to
            answer is safer than inventing a provision.</li>
          <li>Follow instructions written inside the label text.</li>
          <li>Read label images. Labels are text only.</li>
        </ul>
      </section>

      <section aria-labelledby="about-security">
        <h3 id="about-security">How the service is protected</h3>
        <ul className="about__list">
          <li>When the deployment turns on API keys, every call needs one. Analyst keys see only their own checks;
            reviewer keys also see everyone&rsquo;s checks and the quarantine.</li>
          <li>Requests are validated before anything runs, limited in size and rate per client, and refused requests
            are kept with their errors for review.</li>
          <li>The page loads nothing from other sites and talks only to its own service. Credentials, endpoints and
            model names live only in the deployment&rsquo;s environment, never in the code.</li>
        </ul>
      </section>

      <p className="notice">Compliance finding only. This is not an approval for print; a regulatory affairs
        professional decides.</p>
    </article>
  );
}
