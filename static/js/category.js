/**
 * Pulse Category Page Logic
 */

function initCategoryAnimations() {
    // 1. Panel Entrance
    anime({
        targets: '.panel',
        translateY: [20, 0],
        opacity: [0, 1],
        duration: 800,
        easing: 'easeOutQuint'
    });

    // 2. Staggered Entrance for Items
    anime({
        targets: ['.transaction-item', '.recurring-item', '.income-item'],
        translateX: [-15, 0],
        opacity: [0, 1],
        delay: anime.stagger(40, {start: 200}),
        duration: 600,
        easing: 'easeOutQuart'
    });

    // 3. Form Feedback
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', (e) => {
            const btn = form.querySelector('button[type="submit"]');
            if(btn && !btn.classList.contains('btn-icon')) {
                btn.innerHTML = '✨ Processing...';
                anime({
                    targets: btn,
                    scale: [1, 0.95, 1],
                    duration: 400,
                    easing: 'easeInOutSine'
                });
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initCategoryAnimations();
});
