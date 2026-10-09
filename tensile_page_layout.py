"""Browser-only, content-sized page layout; no analysis or kernel callbacks."""
import anywidget


class ContentWidth(anywidget.AnyWidget):
    """Wrap prose, but reserve the natural width of visible tables/plot cards."""
    _esm = """
    export default {render({el}) {
      Object.assign(el.style, {height:'0px', minHeight:'0px', width:'100%',
        margin:'0', padding:'0', overflow:'hidden', flex:'0 0 0px'});
      let page, timer, disposed=false;
      const pixels = value => Number.parseFloat(value) || 0;
      const visible = node => node.getClientRects().length && node.getBoundingClientRect().height > 0;
      // Include accordion/tab padding and borders, not the stretched widths
      // of their parents. Those widths are outputs of this calculation.
      const surround = node => {
        let total=0;
        for (let parent=node.parentElement; parent; parent=parent.parentElement) {
          const css=getComputedStyle(parent);
          total += pixels(css.paddingLeft)+pixels(css.paddingRight)
                 + pixels(css.borderLeftWidth)+pixels(css.borderRightWidth);
          if (parent===page) break;
        }
        return total;
      };
      const schedule = () => {
        if (!disposed && timer===undefined) timer=setTimeout(measure, 80);
      };
      const mutations = new MutationObserver(changes => {
        // Our own width update is not a new content requirement.
        if (changes.some(c => !(c.target===page && c.attributeName==='style'))) schedule();
      });
      const resize = new ResizeObserver(schedule);
      const measure = () => {
        timer=undefined;
        if (disposed) return;
        if (!page) {
          page=el.closest('.tw-webapp');
          if (!page) return; // ResizeObserver retries when the widget is attached.
          mutations.observe(page, {subtree:true, childList:true, characterData:true,
            attributes:true, attributeFilter:['style','class','hidden','aria-expanded']});
        }
        const css=getComputedStyle(page);
        // Existing settings are capped at 980px; long explanatory paragraphs
        // should wrap there rather than dictate the whole page's width.
        let wanted=980+pixels(css.paddingLeft)+pixels(css.paddingRight);
        page.querySelectorAll('.tw-summary table, .tw-specimens table').forEach(table => {
          if (visible(table)) wanted=Math.max(wanted, table.getBoundingClientRect().width+surround(table));
        });
        page.querySelectorAll('.tw-plot-board').forEach(board => {
          if (!visible(board)) return;
          const cards=Array.from(board.children).filter(visible);
          if (!cards.length) return;
          const width=pixels(cards[0].style.maxWidth);
          if (!width) return;
          const boardStyle=getComputedStyle(board);
          const gap=pixels(boardStyle.columnGap);
          const configured=pixels(board.style.maxWidth);
          // Preserve auto layout's current column count at the requested card
          // width; explicit layouts retain their selected column/plot sizes.
          const tracks=boardStyle.gridTemplateColumns.match(/[\\d.]+px/g) || [];
          const columns=Math.max(1,Math.min(cards.length,tracks.length));
          const natural=cards.length*width+Math.max(0,cards.length-1)*gap;
          const preferred=Math.min(natural, configured || columns*width+(columns-1)*gap);
          wanted=Math.max(wanted, preferred+surround(board));
        });
        const value=Math.ceil(wanted)+'px';
        if (page.style.getPropertyValue('--tw-content-width')!==value)
          page.style.setProperty('--tw-content-width',value);
      };
      resize.observe(el);
      window.addEventListener('resize',schedule);
      schedule();
      return () => {disposed=true; clearTimeout(timer); resize.disconnect(); mutations.disconnect();
        window.removeEventListener('resize',schedule);};
    }};
    """
