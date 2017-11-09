
import os

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = '0'

from deepneuro.data.data_collection import DataCollection
from deepneuro.augmentation.augment import Flip_Rotate_2D, ExtractPatches, MaskData, Downsample, ChooseData
from deepneuro.models.unet import UNet
from deepneuro.models.timenet import TimeNet
from deepneuro.outputs.inference import ModelPatchesInference
from deepneuro.models.model import load_old_model

# Temporary
from keras.utils import plot_model
import glob

def train_Segment_GBM(data_directory, val_data_directory):

    # Define input modalities to load.
    training_modality_dict = {'input_modalities': 
    ['*FLAIR*', ['*T2SPACE*', '*T2_pp*'], ['*T1_pp.*', '*MPRAGE_Pre*'], ['*T1post_pp.*', '*MPRAGE_POST*'], ['enhancing*'], ['wholetumor*', 'full_edemamask*']],
    'ground_truth': [['enhancing*'], ['wholetumor*', 'full_edemamask*']]}

    load_data = False
    train_model = False
    load_test_data = True
    predict = True

    training_data = '/mnt/jk489/QTIM_Databank/DeepNeuro_Datasets/enhancing_label_upsampling_323232.h5'
    model_file = 'label_upsampling_323232_model_correct.h5'
    testing_data = './FLAIR_upsampling_323232_test.h5'

    # Write the data to hdf5
    if (not os.path.exists(training_data) and train_model) or load_data:

        # Create a Data Collection
        training_data_collection = DataCollection(data_directory, modality_dict=training_modality_dict, verbose=True)
        training_data_collection.fill_data_groups()

        # Define patch sampling regions
        def brain_region(data):
            return (data['ground_truth'] != 1) & (data['input_modalities'] != 0)
        def roi_region(data):
            return data['ground_truth'] == 1

        # Add patch augmentation
        patch_augmentation = ExtractPatches(patch_shape=(32, 32, 32), patch_region_conditions=[[roi_region, 1]], data_groups=['input_modalities', 'ground_truth'], patch_dimensions={'ground_truth': [0,1,2], 'input_modalities': [0,1,2]})
        training_data_collection.append_augmentation(patch_augmentation, multiplier=70)

        # Write data to hdf5
        training_data_collection.write_data_to_file(training_data)

    if train_model:
        # Or load pre-loaded data.
        training_data_collection = DataCollection(data_storage=training_data, verbose=True)
        training_data_collection.fill_data_groups()

        # Choose a modality
        choice_augmentation = ChooseData(axis={'input_modalities': -1, 'ground_truth': -1}, choices=[-1,-2], data_groups=['input_modalities', 'ground_truth'], random_sample=False)
        training_data_collection.append_augmentation(choice_augmentation, multiplier=2)

        # Add down-sampling
        mask_augmentation = Downsample(channel=4, axes={'input_modalities': [-4,-3,-2]}, factor=3, data_groups=['input_modalities'])
        training_data_collection.append_augmentation(mask_augmentation, multiplier=4)

        # Add left-right flips
        flip_augmentation = Flip_Rotate_2D(flip=True, rotate=False, data_groups=['input_modalities', 'ground_truth'])
        training_data_collection.append_augmentation(flip_augmentation, multiplier=2)

        # Define model parameters
        model_parameters = {'input_shape': (32, 32, 32, 5),
                        'downsize_filters_factor': 1,
                        'pool_size': (2, 2, 2), 
                        'filter_shape': (5, 5, 5), 
                        'dropout': 0, 
                        'batch_norm': True, 
                        'initial_learning_rate': 0.000001, 
                        'output_type': 'binary_label',
                        'num_outputs': 1, 
                        'activation': 'relu',
                        'padding': 'same', 
                        'implementation': 'keras',
                        'depth': 4,
                        'max_filter': 512}

        # Create U-Net
        unet_model = UNet(**model_parameters)
        plot_model(unet_model.model, to_file='model_image_dn.png', show_shapes=True)
        training_parameters = {'input_groups': ['input_modalities', 'ground_truth'],
                        'output_model_filepath': model_file,
                        'training_batch_size': 64,
                        'num_epochs': 1000,
                        'training_steps_per_epoch': 20}
        unet_model.train(training_data_collection, **training_parameters)
    else:
        unet_model = load_old_model(model_file)

    # Load testing data..
    if not os.path.exists(testing_data) or load_test_data:
        # Create a Data Collection
        testing_data_collection = DataCollection(val_data_directory, modality_dict=training_modality_dict, verbose=True)
        testing_data_collection.fill_data_groups()
        # Write data to hdf5
        testing_data_collection.write_data_to_file(testing_data)

    if predict:
        testing_data_collection = DataCollection(data_storage=testing_data, verbose=True)
        testing_data_collection.fill_data_groups()

        # Choose a modality
        choice_augmentation = ChooseData(axis={'input_modalities': -1, 'ground_truth': -1}, choices=[-1,-2], data_groups=['input_modalities', 'ground_truth'], random_sample=False)
        testing_data_collection.append_augmentation(choice_augmentation, multiplier=2)

        # Add down-sampling
        mask_augmentation = Downsample(channel=4, axes={'input_modalities': [-4,-3,-2]}, factor=3, data_groups=['input_modalities'], random_sample=False)
        testing_data_collection.append_augmentation(mask_augmentation, multiplier=3)

        testing_parameters = {'inputs': ['input_modalities'], 
                        'output_filename': 'deepneuro-label.nii.gz',
                        'batch_size': 250,
                        'patch_overlaps': 6,
                        'output_patch_shape': (26,26,26,4)}

        prediction = ModelPatchesInference(testing_data_collection, **testing_parameters)

        unet_model.append_output([prediction])
        unet_model.generate_outputs()


if __name__ == '__main__':

    data_directory = '/mnt/jk489/QTIM_Databank/QTIM_CLINICAL/Preprocessed/Train'
    val_data_directory = '/mnt/jk489/QTIM_Databank/QTIM_CLINICAL/Preprocessed/Test_Case'

    train_Segment_GBM(data_directory, val_data_directory)