export const capitalizeWords = (str) => {
    if (!str) return '';

    return str
        .split('-')
        .map(segment =>
            segment
                .split(' ')
                .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                .join(' ')
        )
        .join('-');
};
