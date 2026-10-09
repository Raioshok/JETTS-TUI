import { useLayoutEffect, useRef, type ReactNode } from "react";
import { gsap } from "gsap";

// The first page of a visit gets a staged entrance (an infrequent brand
// moment); later navigations get one short fade-up so routine route changes
// never feel slow.
let firstEntranceDone = false;

const MAX_STAGGERED = 8;

/**
 * Animates a routed page in once it has actually mounted. Rendered inside the
 * route's Suspense boundary, so the layout effect runs with the lazy page
 * already in the DOM. Respects `prefers-reduced-motion` and clears every
 * inline style it sets, so no lingering transform breaks `position: fixed`
 * descendants.
 */
export function PageEnter({ children }: { children: ReactNode }) {
  const scope = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const root = scope.current;
    if (!root) return;

    const staged = !firstEntranceDone;
    firstEntranceDone = true;

    // Scoped matchMedia: animations only run without reduced motion, and
    // revert() undoes them (and clears tweens) on unmount.
    const mm = gsap.matchMedia(root);
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      const pages = Array.from(root.children) as HTMLElement[];
      if (pages.length === 0) return;

      if (!staged) {
        gsap.from(pages, {
          autoAlpha: 0,
          y: 6,
          duration: 0.24,
          ease: "power2.out",
          clearProps: "opacity,visibility,transform",
        });
        return;
      }

      // Stagger the page's top-level sections (header, cards, …) ~100ms
      // apart so the hierarchy reads in order.
      const sections =
        pages.length === 1 && pages[0].children.length > 1
          ? (Array.from(pages[0].children) as HTMLElement[])
          : pages;
      gsap.from(sections.slice(0, MAX_STAGGERED), {
        autoAlpha: 0,
        y: 10,
        duration: 0.45,
        ease: "power3.out",
        stagger: 0.1,
        clearProps: "opacity,visibility,transform",
      });
    });

    return () => mm.revert();
  }, []);

  return (
    <div ref={scope} className="contents">
      {children}
    </div>
  );
}
