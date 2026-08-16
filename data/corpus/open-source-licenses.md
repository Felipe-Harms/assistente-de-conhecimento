# Open Source License Primer

Open source licenses define the rights and obligations that come with
using, modifying, and distributing software. Choosing the right license
is one of the most consequential decisions an open source project
makes.

## Permissive Licenses

MIT and BSD-2-Clause are the most permissive. They allow almost any
use, including commercial closed-source forks, with the only obligation
being to preserve the copyright notice. Apache-2.0 adds an explicit
patent grant and a patent retaliation clause.

## Copyleft Licenses

GPL-3.0 requires derivative works to be distributed under the same
license. This is "strong copyleft". LGPL-3.0 is weaker — it allows
linking from proprietary code without imposing GPL on the larger work.

## Business Considerations

- MIT and BSD-2 are popular in corporate adoption because they impose
  the fewest downstream restrictions.
- GPL is more common in infrastructure and tooling projects that want
  to keep derivative work open.
- Apache-2.0 is the standard at many large foundations (Apache,
  Kubernetes, TensorFlow).

## Compatibility

Not all licenses are compatible. GPL-2.0 code, for example, cannot be
combined with Apache-2.0 code in some configurations because of
patent clauses. The Free Software Foundation maintains a compatibility
matrix that should be consulted before mixing licenses.

## Adding a License

To license a project, add a `LICENSE` file at the repository root and
update the README to reference the chosen license. A missing license
defaults to "all rights reserved" in most jurisdictions.
