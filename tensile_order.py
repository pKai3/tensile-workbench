"""Presentation-only group ordering; never changes specimen eligibility."""


def ordered_groups(groups, preferred=()):
    """Keep available identities in saved order; append other groups as supplied."""
    selected = set(groups)
    return list(dict.fromkeys([g for g in preferred if g in selected] + list(groups)))


def validate_group_order(order):
    if (not isinstance(order, list) or any(not isinstance(g, str) or not g for g in order)
            or len(set(order)) != len(order)):
        raise ValueError('Group order must be a list of unique group names.')


def sort_group_frame(frame, order=(), *, descending=False):
    """Stable display/export sort, preserving all values and within-group rows."""
    if frame.empty or 'Group' not in frame:
        return frame
    groups = ordered_groups(sorted(frame['Group'].drop_duplicates()), order)
    ranks = {group: index for index, group in enumerate(groups)}
    return frame.sort_values('Group', key=lambda values: values.map(ranks),
                             ascending=not descending, kind='stable')
