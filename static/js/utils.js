/**
 * Pulse Utility Functions
 * Shared logic for modals, alerts, and common interactions.
 */

/**
 * Open a modal by ID
 * @param {string} id - The ID of the modal overlay element
 */
function openModal(id) {
    const modalOverlay = document.getElementById(id);
    if (modalOverlay) {
        modalOverlay.style.opacity = 0;
        modalOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        
        const modal = modalOverlay.querySelector('.modal');
        if (modal) {
            modal.style.opacity = 0;
            modal.style.transform = 'translateY(20px) scale(0.95)';
        }

        anime({
            targets: modalOverlay,
            opacity: [0, 1],
            duration: 250,
            easing: 'linear'
        });

        if (modal) {
            anime({
                targets: modal,
                opacity: [0, 1],
                translateY: [20, 0],
                scale: [0.95, 1],
                duration: 400,
                easing: 'easeOutQuint'
            });
        }
    }
}

/**
 * Close a modal by ID
 * @param {string} id - The ID of the modal overlay element
 */
function closeModal(id) {
    const modalOverlay = document.getElementById(id);
    if (modalOverlay) {
        const modal = modalOverlay.querySelector('.modal');
        
        anime({
            targets: modalOverlay,
            opacity: [1, 0],
            duration: 250,
            easing: 'linear',
            complete: () => {
                modalOverlay.classList.remove('active');
                modalOverlay.style.opacity = '';
            }
        });

        if (modal) {
            anime({
                targets: modal,
                opacity: [1, 0],
                translateY: [0, 15],
                scale: [1, 0.95],
                duration: 250,
                easing: 'easeInQuint',
                complete: () => {
                    modal.style.transform = '';
                    modal.style.opacity = '';
                }
            });
        }
        document.body.style.overflow = '';
    }
}

/**
 * Select a category in the Add/Edit Expense modals
 * @param {string} id - Category ID
 * @param {HTMLElement} el - Clicked element
 * @param {string} containerId - Container ID to scope the selection
 * @param {string} inputId - Hidden input ID to update
 */
function handleCategorySelection(id, el, containerId, inputId) {
    const input = document.getElementById(inputId);
    if (input) input.value = id;
    
    const container = document.getElementById(containerId);
    if (container) {
        container.querySelectorAll('.category-select-item').forEach(item => {
            item.classList.remove('active');
        });
    }
    el.classList.add('active');
}

// Global Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss flash messages
    setTimeout(() => {
        const container = document.getElementById('flash-container');
        if (container) container.remove();
    }, 3500);

    // Close modal on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeModal(overlay.id);
            }
        });
    });

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(m => {
                closeModal(m.id);
            });
        }
    });

    // Input focus micro-interactions
    document.querySelectorAll('.form-input, .form-textarea').forEach(input => {
        input.addEventListener('focus', () => {
            anime({
                targets: input,
                scale: 1.01,
                boxShadow: '0 0 0 2px rgba(167, 139, 250, 0.3)',
                duration: 250,
                easing: 'easeOutSine'
            });
            const label = input.previousElementSibling;
            if (label && label.classList.contains('form-label')) {
                anime({
                    targets: label,
                    color: '#A78BFA',
                    duration: 250,
                    easing: 'easeOutSine'
                });
            }
        });
        
        input.addEventListener('blur', () => {
            anime({
                targets: input,
                scale: 1,
                boxShadow: '0 0 0 0px rgba(167, 139, 250, 0)',
                duration: 250,
                easing: 'easeOutSine'
            });
            const label = input.previousElementSibling;
            if (label && label.classList.contains('form-label')) {
                anime({
                    targets: label,
                    color: '#9c9480',
                    duration: 250,
                    easing: 'easeOutSine'
                });
            }
        });
    });
});

/**
 * Fetch expense data and open the edit modal
 * @param {number} expenseId - The ID of the expense to edit
 */
async function openEditModal(expenseId) {
    try {
        const res = await fetch(`/api/expense/${expenseId}`);
        const data = await res.json();

        const form = document.getElementById('edit-expense-form');
        if (form) form.action = `/expense/edit/${expenseId}`;
        
        const descInput = document.getElementById('edit-expense-desc');
        if (descInput) descInput.value = data.description;
        
        const amountInput = document.getElementById('edit-expense-amount');
        if (amountInput) amountInput.value = data.amount;
        
        const dateInput = document.getElementById('edit-expense-date');
        if (dateInput) dateInput.value = data.date;
        
        const noteInput = document.getElementById('edit-expense-note');
        if (noteInput) noteInput.value = data.note || '';
        
        const categoryInput = document.getElementById('edit-expense-category');
        if (categoryInput) categoryInput.value = data.category;

        // Highlight correct category in the grid
        const grid = document.getElementById('edit-category-grid');
        if (grid) {
            grid.querySelectorAll('.category-select-item').forEach(item => {
                item.classList.remove('active');
                if (item.dataset.category === data.category) {
                    item.classList.add('active');
                }
            });
        }

        openModal('edit-expense-modal');
    } catch (err) {
        console.error('Failed to load expense:', err);
    }
}
